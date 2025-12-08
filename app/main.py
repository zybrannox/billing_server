from typing import List
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, APIRouter, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pymongo import MongoClient
from bson import ObjectId
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from fastapi.responses import StreamingResponse
from googleapiclient.http import MediaIoBaseDownload
from dotenv import load_dotenv
from app.models import Project
import os, io, json
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


# # Load environment variables from .env
# load_dotenv()

# # MongoDB connection
mongo_uri = os.getenv("MONGO_URI")
client = MongoClient(mongo_uri, tls=True, tlsAllowInvalidCertificates=True)
db = client.project_db
collection = db.projects

app = FastAPI()
router = APIRouter()

CLIENT_SECRETS_FILE = "client_secrets.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
REDIRECT_URI = "http://localhost:8080/oauth2callback"
BILLING_FOLDER_ID = "1Tl31zYoMIny_t600Ca3H63IjlILlyvsn"
UPLOAD_FOLDER = "./Billing/"


# # CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://taskmanager-three-blush.vercel.app",  # production
        "http://localhost:5173",  # frontend dev
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

flow = Flow.from_client_secrets_file(
    CLIENT_SECRETS_FILE,
    scopes=SCOPES,
    redirect_uri=REDIRECT_URI,
)

# Persistent store
TOKEN_FILE = "tokens.json"


def save_credentials(creds):
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())


def load_credentials():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            return Credentials.from_authorized_user_info(data, SCOPES)
    return None


@app.get("/authorize")
def authorize():
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # ensures refresh token comes every time
    )
    return RedirectResponse(auth_url)


@app.get("/oauth2callback")
def oauth2callback(request: Request):
    try:
        code = request.query_params.get("code")
        flow.fetch_token(code=code)

        credentials = flow.credentials
        save_credentials(credentials)

        return {"success": True, "message": "OAuth setup complete!"}

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "OAuth callback failed", "details": str(e)},
        )

@app.post("/upload-image")
async def upload_multiple(files: List[UploadFile] = File(...)):
    creds = load_credentials()
    if not creds:
        raise HTTPException(401, "Not authorized. Visit /authorize first.")

    drive_service = build("drive", "v3", credentials=creds)
    uploaded_files = []

    for file in files:
<<<<<<< HEAD
        try:
            # Read incoming file into bytes
            file_bytes = await file.read()
            filename = file.filename.rsplit(".", 1)[0]

            result = cloudinary.uploader.upload(
                file_bytes,
                folder="portfolio_projects",
                public_id=filename,
                overwrite=True,  # overwrite if same file exists
                resource_type="image"
            )
=======
        content = await file.read()
        file_stream = io.BytesIO(content)

        media = MediaIoBaseUpload(file_stream, mimetype=file.content_type)
        metadata = {"name": file.filename, "parents": [BILLING_FOLDER_ID]}
>>>>>>> 4cfa992 (server)

        upload = drive_service.files().create(
            body=metadata, media_body=media, fields="id"
        ).execute()

        file_id = upload["id"]

        # Set file permission
        user_email = "zybrannox@gmail.com"
        drive_service.permissions().create(
            fileId=file_id,
            body={
                "type": "user",
                "role": "reader",
                "emailAddress": user_email
            }
        ).execute()

        uploaded_files.append({
            "id": file_id,
            "name": file.filename
        })

    return {"files": uploaded_files}

# # Create a new project
@app.post("/projects/")
async def create_project(project: Project):
    collection.insert_one(project.model_dump())
    return {"message": "Project added successfully!"}

# Get all projects
@app.get("/projects/")
async def get_projects():
    projects = list(collection.find({}))
    for project in projects:
        project["_id"] = str(project["_id"])
    return JSONResponse(content=projects)

@app.delete("/projects/{project_id}")
async def delete_project(project_id: str = Path(..., description="The ID of the project to delete")):
    result = collection.delete_one({"_id": ObjectId(project_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "Project deleted successfully!"}

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail)}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "details": str(exc)}
    )

@app.get("/download/{file_id}")
async def download_drive_file(file_id: str):
    creds = load_credentials()
    if not creds:
        return JSONResponse(
            status_code=401,
            content={"error": "Not authorized. Visit /authorize first."}
        )

    try:
        drive_service = build("drive", "v3", credentials=creds)

        # Step 1: GET metadata first
        try:
            meta = drive_service.files().get(
                fileId=file_id,
                fields="id, name, mimeType"
            ).execute()
        except Exception as e:
            return JSONResponse(
                status_code=404,
                content={"error": "File not found or permission denied", "details": str(e)}
            )

        file_name = meta["name"]
        mime_type = meta["mimeType"]

        # Step 2: Download the file
        request = drive_service.files().get_media(fileId=file_id)
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        file_stream.seek(0)

        return StreamingResponse(
            file_stream,
            media_type=mime_type,
            headers={"Content-Disposition": f'attachment; filename="{file_name}"'}
        )

    except Exception as e:
        # Catch **any unexpected Google API HTML responses**
        return JSONResponse(
            status_code=500,
            content={"error": "Drive download failed", "details": str(e)}
        )

# Include router
app.include_router(router)
