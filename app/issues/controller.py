from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.audit.service import record as record_audit
from app.auth.dependencies import get_current_user, require_admin
from app.database import get_db
from app.datetime_utils import utcnow
from app.entities import Issue, User
from app.errors import NotFound
from app.rate_limiting import limiter

from .model import IssueCreate, IssueListResponse, IssueRead, IssueStatus, IssueUpdate, MyIssuesResponse

router = APIRouter(prefix="/issues", tags=["Issues"])

# Enough to scroll back through in the helper's small panel.
MY_ISSUES_LIMIT = 30


def _my_id(db: Session, current_user: dict) -> int:
    return db.query(User.id).filter(User.username == current_user["username"]).scalar()


def _mine(db: Session, current_user: dict):
    return db.query(Issue).filter(Issue.reported_by_id == _my_id(db, current_user))


@router.post("/", response_model=IssueRead)
@limiter.limit("30/hour")
def report_issue(
    request: Request,
    response: Response,
    payload: IssueCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    issue = Issue(text=payload.text, reported_by_id=_my_id(db, current_user), reported_by=current_user["username"])
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue


@router.get("/mine", response_model=MyIssuesResponse)
def my_issues(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    items = _mine(db, current_user).order_by(Issue.created_at.desc(), Issue.id.desc()).limit(MY_ISSUES_LIMIT).all()
    # Counted separately so an old solved issue past the limit can't be missed.
    unseen_count = _mine(db, current_user).filter(Issue.is_done.is_(True), Issue.done_seen_at.is_(None)).count()
    return {"items": items, "unseen_count": unseen_count}


@router.post("/mine/seen")
def mark_mine_seen(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    now = utcnow()
    _mine(db, current_user).filter(Issue.is_done.is_(True), Issue.done_seen_at.is_(None)).update(
        {Issue.done_seen_at: now}, synchronize_session=False
    )
    db.commit()
    return {"message": "Marked as seen"}


@router.get("/", response_model=IssueListResponse)
def list_issues(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[IssueStatus] = None,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    query = db.query(Issue)
    if status:
        query = query.filter(Issue.is_done.is_(status == "done"))
    total = query.count()
    # What still needs doing comes first; solved ones with the latest on top.
    items = (
        query.order_by(Issue.is_done.asc(), Issue.done_at.desc(), Issue.created_at.desc(), Issue.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    counts = dict(db.query(Issue.is_done, func.count(Issue.id)).group_by(Issue.is_done).all())
    return {"items": items, "total": total, "open_count": counts.get(False, 0), "done_count": counts.get(True, 0)}


@router.patch("/{issue_id}", response_model=IssueRead)
def update_issue(
    issue_id: int,
    payload: IssueUpdate,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    issue = db.get(Issue, issue_id)
    if not issue:
        raise NotFound("Issue")

    if payload.is_done != issue.is_done:
        issue.is_done = payload.is_done
        issue.done_at = utcnow() if payload.is_done else None
        issue.done_by = _admin["username"] if payload.is_done else None
        # Solving it again later is news again.
        issue.done_seen_at = None
        db.commit()
        db.refresh(issue)
        action = "issue.done" if payload.is_done else "issue.reopen"
        record_audit(db, _admin["username"], action, "issue", issue.id, {"label": issue.text[:120]})
    return issue
