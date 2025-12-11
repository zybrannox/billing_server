# from typing import List
# from fastapi import FastAPI, Request, HTTPException, UploadFile, File, APIRouter, Path
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
# from pymongo import MongoClient
# from bson import ObjectId
# from google_auth_oauthlib.flow import Flow
# from google.oauth2.credentials import Credentials
# from google.auth.transport.requests import Request as GoogleAuthRequest
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
# from dotenv import load_dotenv
# from app.models import Project
# import os, io, json, logging
# from starlette.exceptions import HTTPException as StarletteHTTPException


# # # Load environment variables from .env
# # load_dotenv()

# # # MongoDB connection
# mongo_uri = os.getenv("MONGO_URI")
# client = MongoClient(mongo_uri, tls=True, tlsAllowInvalidCertificates=True)
# db = client.project_db
# collection = db.projects

# app = FastAPI()
# router = APIRouter()

# CLIENT_SECRETS_FILE = "client_secrets.json"
# SCOPES = ["https://www.googleapis.com/auth/drive.file"]
# REDIRECT_URI = "http://localhost:8080/oauth2callback"
# BILLING_FOLDER_ID = "1Tl31zYoMIny_t600Ca3H63IjlILlyvsn"
# UPLOAD_FOLDER = "./Billing/"


# # # CORS middleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         "https://taskmanager-three-blush.vercel.app",  # production
#         "http://localhost:5173",  # frontend dev
#     ],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# flow = Flow.from_client_secrets_file(
#     CLIENT_SECRETS_FILE,
#     scopes=SCOPES,
#     redirect_uri=REDIRECT_URI,
# )

# # Persistent store
# TOKEN_FILE = "tokens.json"


# def save_credentials(creds):
#     with open(TOKEN_FILE, "w") as f:
#         f.write(creds.to_json())


# def load_credentials():
#     if os.path.exists(TOKEN_FILE):
#         with open(TOKEN_FILE, "r") as f:
#             data = json.load(f)
#             return Credentials.from_authorized_user_info(data, SCOPES)
#     return None


# @app.get("/authorize")
# def authorize():
#     auth_url, state = flow.authorization_url(
#         access_type="offline",
#         include_granted_scopes="true",
#         prompt="consent",  # ensures refresh token comes every time
#     )
#     return RedirectResponse(auth_url)


# @app.get("/oauth2callback")
# def oauth2callback(request: Request):
#     try:
#         code = request.query_params.get("code")
#         flow.fetch_token(code=code)

#         credentials = flow.credentials
#         save_credentials(credentials)

#         return {"success": True, "message": "OAuth setup complete!"}

#     except Exception as e:
#         return JSONResponse(
#             status_code=500,
#             content={"error": "OAuth callback failed", "details": str(e)},
#         )

# @app.post("/upload-image")
# async def upload_multiple(files: List[UploadFile] = File(...)):
#     creds = load_credentials()
#     if not creds:
#         raise HTTPException(401, "Not authorized. Visit /authorize first.")

#     drive_service = build("drive", "v3", credentials=creds)
#     uploaded_files = []

#     for file in files:
#         content = await file.read()
#         file_stream = io.BytesIO(content)

#         media = MediaIoBaseUpload(file_stream, mimetype=file.content_type)
#         metadata = {"name": file.filename, "parents": [BILLING_FOLDER_ID]}

#         upload = drive_service.files().create(
#             body=metadata, media_body=media, fields="id"
#         ).execute()

#         file_id = upload["id"]

#         # Set file permission
#         user_email = "zybrannox@gmail.com"
#         drive_service.permissions().create(
#             fileId=file_id,
#             body={
#                 "type": "user",
#                 "role": "reader",
#                 "emailAddress": user_email
#             }
#         ).execute()

#         uploaded_files.append({
#             "id": file_id,
#             "name": file.filename
#         })

#     return {"files": uploaded_files}

# # # Create a new project
# @app.post("/projects/")
# async def create_project(project: Project):
#     collection.insert_one(project.model_dump())
#     return {"message": "Project added successfully!"}

# # Get all projects
# @app.get("/projects/")
# async def get_projects():
#     projects = list(collection.find({}))
#     for project in projects:
#         project["_id"] = str(project["_id"])
#     return JSONResponse(content=projects)

# @app.delete("/projects/{project_id}")
# async def delete_project(project_id: str = Path(..., description="The ID of the project to delete")):
#     result = collection.delete_one({"_id": ObjectId(project_id)})
#     if result.deleted_count == 0:
#         raise HTTPException(status_code=404, detail="Project not found")
#     return {"message": "Project deleted successfully!"}

# @app.exception_handler(StarletteHTTPException)
# async def http_exception_handler(request: Request, exc: StarletteHTTPException):
#     return JSONResponse(
#         status_code=exc.status_code,
#         content={"error": str(exc.detail)}
#     )

# @app.exception_handler(Exception)
# async def general_exception_handler(request: Request, exc: Exception):
#     return JSONResponse(
#         status_code=500,
#         content={"error": "Internal server error", "details": str(exc)}
#     )

# @app.get("/download/{file_id}")
# async def download_drive_file(file_id: str):
#     creds = load_credentials()
#     if not creds:
#         return JSONResponse(
#             status_code=401,
#             content={"error": "Not authorized. Visit /authorize first."}
#         )

#     try:
#         drive_service = build("drive", "v3", credentials=creds)

#         # Step 1: GET metadata first
#         try:
#             meta = drive_service.files().get(
#                 fileId=file_id,
#                 fields="id, name, mimeType"
#             ).execute()
#         except Exception as e:
#             return JSONResponse(
#                 status_code=404,
#                 content={"error": "File not found or permission denied", "details": str(e)}
#             )

#         file_name = meta["name"]
#         mime_type = meta["mimeType"]

#         # Step 2: Download the file
#         request = drive_service.files().get_media(fileId=file_id)
#         file_stream = io.BytesIO()
#         downloader = MediaIoBaseDownload(file_stream, request)

#         done = False
#         while not done:
#             status, done = downloader.next_chunk()

#         file_stream.seek(0)

#         return StreamingResponse(
#             file_stream,
#             media_type=mime_type,
#             headers={"Content-Disposition": f'attachment; filename="{file_name}"'}
#         )

#     except Exception as e:
#         # Catch **any unexpected Google API HTML responses**
#         return JSONResponse(
#             status_code=500,
#             content={"error": "Drive download failed", "details": str(e)}
#         )

# # Include router
# app.include_router(router)


"""
Production-ready FastAPI app for Google Drive OAuth + file upload/download
- Generates client_secrets.json at startup from environment variables
- Stores OAuth tokens in MongoDB (persistent across restarts)
- Refreshes tokens when needed
- Uses env-based CORS origins
- Suitable for Railway / any containerized host

Deploy instructions (short):
1. Set environment variables in Railway (see REQUIRED_ENV list below)
2. Deploy this app. It will create client_secrets.json on startup.
3. Visit /authorize once to complete OAuth and store tokens in MongoDB.

Required ENV variables (example names):
- MONGO_URI
- GOOGLE_CLIENT_ID
- GOOGLE_CLIENT_SECRET
- GOOGLE_REDIRECT_URI
- GOOGLE_AUTH_URI (optional, default uses Google's)
- GOOGLE_TOKEN_URI (optional)
- GOOGLE_CERT_URL (optional)
- BILLING_FOLDER_ID
- ALLOWED_ORIGINS (comma-separated list)
- RAILWAY_STATIC_URL (optional for JS origins)

"""

from typing import List, Optional
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, APIRouter, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pymongo import MongoClient
from bson import ObjectId
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from dotenv import load_dotenv
from app.models import Project
import os, io, json, logging
from starlette.exceptions import HTTPException as StarletteHTTPException

# Load local .env if present (development). In production Railway env vars are used.
load_dotenv(override=False)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Environment / defaults ---
CLIENT_SECRETS_FILE = os.getenv("CLIENT_SECRETS_FILE", "client_secrets.json")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080/oauth2callback")
GOOGLE_AUTH_URI = os.getenv("GOOGLE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth")
GOOGLE_TOKEN_URI = os.getenv("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")
GOOGLE_CERT_URL = os.getenv("GOOGLE_CERT_URL", "https://www.googleapis.com/oauth2/v1/certs")

BILLING_FOLDER_ID = os.getenv("BILLING_FOLDER_ID")
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "./Billing/")

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

# MongoDB
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable is required")

client = MongoClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=True)
db = client.project_db
collection = db.projects
# token storage collection
token_collection = db.oauth_tokens

app = FastAPI(title="FastAPI Google Drive (production-ready)")
router = APIRouter()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Utility: create client_secrets.json from env
def create_client_secrets_file(path: str = CLIENT_SECRETS_FILE):
    if os.path.exists(path):
        logger.info("client_secrets.json already exists, using it.")
        return

    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
        raise RuntimeError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in environment")

    payload = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "project_id": os.getenv("GOOGLE_PROJECT_ID", "railway-production"),
            "auth_uri": GOOGLE_AUTH_URI,
            "token_uri": GOOGLE_TOKEN_URI,
            "auth_provider_x509_cert_url": GOOGLE_CERT_URL,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uris": [GOOGLE_REDIRECT_URI],
            "javascript_origins": ALLOWED_ORIGINS,
        }
    }

    with open(path, "w") as f:
        json.dump(payload, f)
    logger.info("Wrote client_secrets.json from environment variables")


# Create client secrets on startup
@app.on_event("startup")
async def startup_event():
    create_client_secrets_file()


# OAuth token storage helpers (MongoDB)
TOKEN_DOC_ID = "google_drive_token"

def save_credentials(creds: Credentials):
    # creds.to_json() returns a JSON string; store it as object
    data = json.loads(creds.to_json())
    data["_id"] = TOKEN_DOC_ID
    token_collection.replace_one({"_id": TOKEN_DOC_ID}, data, upsert=True)
    logger.info("Saved OAuth credentials to MongoDB")


def load_credentials() -> Optional[Credentials]:
    doc = token_collection.find_one({"_id": TOKEN_DOC_ID})
    if not doc:
        return None

    # remove _id for Credentials creation
    doc.pop("_id", None)
    creds = Credentials.from_authorized_user_info(doc, SCOPES)

    # If credentials expired and have a refresh token, refresh them
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            save_credentials(creds)
            logger.info("Refreshed OAuth credentials and saved to MongoDB")
        except Exception as e:
            logger.exception("Failed to refresh credentials: %s", e)
            return None

    return creds


# Build Flow factory (use local client_secrets.json created at startup)
def make_flow():
    return Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )


@app.get("/authorize")
def authorize():
    flow = make_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    # store state in DB or let the client manage state if needed
    return RedirectResponse(auth_url)


@app.get("/oauth2callback")
def oauth2callback(request: Request):
    try:
        flow = make_flow()
        code = request.query_params.get("code")
        if not code:
            raise HTTPException(status_code=400, detail="Missing code in callback")

        flow.fetch_token(code=code)
        credentials = flow.credentials
        save_credentials(credentials)

        # return a small success HTML that redirects to your frontend (optional)
        return JSONResponse({"success": True, "message": "OAuth setup complete"})

    except Exception as e:
        logger.exception("OAuth callback failed: %s", e)
        return JSONResponse(status_code=500, content={"error": "OAuth callback failed", "details": str(e)})


@app.post("/upload-image")
async def upload_multiple(files: List[UploadFile] = File(...)):
    creds = load_credentials()
    if not creds:
        raise HTTPException(status_code=401, detail="Not authorized. Visit /authorize first.")

    drive_service = build("drive", "v3", credentials=creds)
    uploaded_files = []

    for file in files:
        content = await file.read()
        file_stream = io.BytesIO(content)

        media = MediaIoBaseUpload(file_stream, mimetype=file.content_type)
        metadata = {"name": file.filename}
        if BILLING_FOLDER_ID:
            metadata["parents"] = [BILLING_FOLDER_ID]

        upload = drive_service.files().create(body=metadata, media_body=media, fields="id,name").execute()
        file_id = upload.get("id")
        name = upload.get("name")

        # Optionally set permissions if you want file accessible to a specific user
        # drive_service.permissions().create(fileId=file_id, body={"type": "user", "role": "reader", "emailAddress": "you@example.com"}).execute()

        uploaded_files.append({"id": file_id, "name": name})

    return {"files": uploaded_files}


# Create a new project
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


@app.get("/download/{file_id}")
async def download_drive_file(file_id: str):
    creds = load_credentials()
    if not creds:
        return JSONResponse(status_code=401, content={"error": "Not authorized. Visit /authorize first."})

    try:
        drive_service = build("drive", "v3", credentials=creds)

        # GET metadata
        try:
            meta = drive_service.files().get(fileId=file_id, fields="id, name, mimeType").execute()
        except Exception as e:
            logger.exception("Failed to get file metadata: %s", e)
            return JSONResponse(status_code=404, content={"error": "File not found or permission denied", "details": str(e)})

        file_name = meta.get("name")
        mime_type = meta.get("mimeType")

        request_media = drive_service.files().get_media(fileId=file_id)
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request_media)

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
        logger.exception("Drive download failed: %s", e)
        return JSONResponse(status_code=500, content={"error": "Drive download failed", "details": str(e)})


# Exception handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"error": "Internal server error", "details": str(exc)})


# Include router (if you add sub-routers later)
app.include_router(router)


# If run as a script for local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fastapi_google_drive_production:app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)), log_level="info")

# --- End of file ---
# Helpful notes:
# - Set ALLOWED_ORIGINS to your front-end URL(s) (comma separated) in Railway.
# - In Google Cloud Console, set the OAuth consent and add the production redirect URI exactly as GOOGLE_REDIRECT_URI.
# - On Railway, add environment variables under "Variables" section.
# - To re-init OAuth (if you need to clear tokens), remove the token document in the oauth_tokens collection or use a small admin endpoint to delete it.
