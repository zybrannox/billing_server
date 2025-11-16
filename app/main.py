from fastapi import FastAPI, HTTPException, UploadFile, File, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pymongo import MongoClient
from typing import List
import os
import cloudinary
import cloudinary.uploader

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

# CORS for production and dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://taskmanager-three-blush.vercel.app",  # your production frontend
        "http://localhost:3000"                         # optional dev
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Project model
class Project(BaseModel):
    name: str
    assignee: str
    started: str
    delivery: str
    status: str
    priority: str
    description: str
    client_status: str
    images: List[str]

# Root route
@app.get("/")
def root():
    return {"message": "Backend running"}

# Upload multiple images to Cloudinary
@router.post("/upload-image")
async def upload_images(files: List[UploadFile] = File(...)):
    uploaded_urls = []
    try:
        for file in files:
            result = cloudinary.uploader.upload(file.file)
            uploaded_urls.append(result["secure_url"])
        return {"urls": uploaded_urls}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cloudinary upload error: {str(e)}")

# Create a new project
@app.post("/projects/")
async def create_project(project: Project):
    collection.insert_one(project.model_dump())
    return {"message": "Project added successfully!"}

# Get all projects
@app.get("/projects/")
async def get_projects():
    projects = list(collection.find({}, {"_id": 0}))
    return JSONResponse(content=projects)

# Include router
app.include_router(router)
