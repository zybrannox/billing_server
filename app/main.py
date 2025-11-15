from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect,APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from pymongo import MongoClient
import cloudinary
import cloudinary.uploader


cloudinary.config( 
    cloud_name = "du9hcdtn0",
    api_key = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET")
)

# MongoDB connection
mongo_uri = os.getenv("MONGO_URI")
client = MongoClient(mongo_uri, tls=True, tlsAllowInvalidCertificates=True)
db = client.project_db
collection = db.projects

app = FastAPI()
router = APIRouter()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://taskmanager-three-blush.vercel.app/"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    images: list[str]

# Root route
@app.get("/")
def root():
    return {"message": "Backend running"}

# upload Image to Cloudinary
@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    try:
        result = cloudinary.uploader.upload(file.file)
        return {"url": result["secure_url"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Create project
@app.post("/projects/")
async def create_project(project: Project):
    try:
        print("Incoming data:", project.dict())   # helpful debug
        collection.insert_one(project.dict())
        return JSONResponse(content={"message": "Project added successfully!"}, status_code=201)
    except Exception as e:
        print("Error inserting:", e)
        raise HTTPException(status_code=500, detail=str(e))

# Get all projects
@app.get("/projects/")
async def get_projects():
    projects = list(collection.find({}, {"_id": 0}))
    return projects

# WebSocket echo test
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Message received: {data}")
    except WebSocketDisconnect:
        print("Client disconnected")
