"""Which uploaded files an invoice actually billed for.

A project can hold files that never made it onto the invoice (references,
rejected drafts), so the invoice's gallery shows only the files its line items
point at (InvoiceItem.project_file_id).

Invoices raised before that link existed have none. For those, a line is
matched to a file by the wording the invoice screen has always generated -
"<project type> – <file name without extension>" - so an old invoice whose
lines still carry their file names keeps showing its files; a line whose
description was rewritten by hand simply matches nothing.
"""
import os

from sqlalchemy.orm import Session

from app.entities import Invoice, ProjectFile


def _stem(name: str | None) -> str:
    return os.path.splitext(name or "")[0].strip().lower()


def invoiced_files(db: Session, invoice: Invoice) -> list[ProjectFile]:
    project_files = (
        db.query(ProjectFile)
        .filter(ProjectFile.project_id == invoice.project_id)
        .order_by(ProjectFile.created_at, ProjectFile.id)
        .all()
    )
    by_id = {f.id: f for f in project_files}

    chosen: list[ProjectFile] = []
    seen: set[int] = set()

    def add(file: ProjectFile | None) -> None:
        if file is not None and file.id not in seen:
            seen.add(file.id)
            chosen.append(file)

    for item in sorted(invoice.items, key=lambda i: (i.sort_order, i.id)):
        if item.project_file_id is not None:
            add(by_id.get(item.project_file_id))
            continue
        description = (item.description or "").strip().lower()
        if not description:
            continue
        for f in project_files:
            stem = _stem(f.original_name)
            if stem and (description == stem or description.endswith(f" – {stem}") or description.endswith(f" - {stem}")):
                add(f)
    return chosen
