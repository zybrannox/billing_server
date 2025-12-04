from typing import List
from fastapi import FastAPI, HTTPException, UploadFile, File, APIRouter, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo import MongoClient
import os
import cloudinary
import cloudinary.uploader
from bson import ObjectId
from app.models import Project
# from dotenv import load_dotenv


# Load environment variables from .env
# load_dotenv()

# Cloudinary config
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# MongoDB connection
mongo_uri = os.getenv("MONGO_URI")
client = MongoClient(mongo_uri, tls=True, tlsAllowInvalidCertificates=True)
db = client.project_db
collection = db.projects

app = FastAPI()
router = APIRouter()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://taskmanager-three-blush.vercel.app",  # production
        "http://localhost:5173",  # frontend dev
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# Root route
@app.get("/")
def root():
    return {"message": "Backend running"}

# Upload multiple images to Cloudinary
@app.post("/upload-image")
async def upload_images(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    uploaded_urls = []

    for file in files:
        try:
            # Read incoming file into bytes
            file_bytes = await file.read()
            original_filename = file.filename

            result = cloudinary.uploader.upload(
                file_bytes,
                folder="portfolio_projects",
                public_id=f"portfolio_projects/{original_filename}",  # full filename
                overwrite=True,  # overwrite if same file exists
                resource_type="image"
            )

            uploaded_urls.append(result["secure_url"])

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Cloudinary upload failed: {str(e)}")

    return {"urls": uploaded_urls}


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

# Include router
app.include_router(router)
