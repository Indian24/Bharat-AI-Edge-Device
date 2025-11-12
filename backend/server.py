import os
import uuid
import base64
import asyncio
from io import BytesIO
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
import json

# Load environment variables
load_dotenv()

app = FastAPI(title="Defect Detective API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
DATABASE_NAME = os.environ.get("DB_NAME", "defect_detective")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DATABASE_NAME]

# Pydantic models
class DefectResult(BaseModel):
    defect_type: str
    confidence: float
    severity: str
    description: str

class AnalysisResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    upload_time: datetime = Field(default_factory=datetime.utcnow)
    total_defects: int
    defects_found: List[DefectResult]
    analysis_complete: bool = True
    image_base64: Optional[str] = None

class AnalysisResponse(BaseModel):
    success: bool
    message: str
    analysis: Optional[AnalysisResult] = None

# Initialize Gemini chat
def create_gemini_chat():
    return LlmChat(
        api_key=GOOGLE_API_KEY,
        session_id=f"defect_analysis_{uuid.uuid4()}",
        system_message="""You are an expert industrial defect detection AI. Analyze images for manufacturing and industrial defects like:
        - Cold joints in welds
        - Foreign materials/contaminants
        - Cracks and fractures  
        - Corrosion and rust
        - Surface imperfections
        - Misaligned components
        - Dimensional issues
        
        Return ONLY a valid JSON response with this exact structure:
        {
            "defects_found": [
                {
                    "defect_type": "Cold Joint",
                    "confidence": 92,
                    "severity": "High",
                    "description": "Incomplete weld penetration detected in joint area"
                },
                {
                    "defect_type": "Foreign Material", 
                    "confidence": 86,
                    "severity": "Medium",
                    "description": "Metallic debris embedded in surface"
                }
            ],
            "total_defects": 2
        }
        
        If no defects are found, return:
        {
            "defects_found": [],
            "total_defects": 0
        }"""
    ).with_model("gemini", "gemini-2.0-flash")

@app.get("/")
async def root():
    return {"message": "Defect Detective API is running"}

@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_defects(file: UploadFile = File(...)):
    try:
        # Validate file type
        if not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Only image files are supported")
        
        # Read and encode image
        contents = await file.read()
        base64_image = base64.b64encode(contents).decode('utf-8')
        
        # Create Gemini chat instance
        chat = create_gemini_chat()
        
        # Create image content
        image_content = ImageContent(image_base64=base64_image)
        
        # Analyze with Gemini
        user_message = UserMessage(
            text="Analyze this manufacturing/industrial image for defects. Return JSON response only.",
            file_contents=[image_content]
        )
        
        # Get analysis result
        response = await chat.send_message(user_message)
        
        # Parse JSON response
        try:
            # Clean up response text
            response_text = response.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            analysis_data = json.loads(response_text)
        except json.JSONDecodeError:
            # Fallback parsing for malformed JSON
            analysis_data = {
                "defects_found": [
                    {
                        "defect_type": "Analysis Error",
                        "confidence": 50,
                        "severity": "Unknown", 
                        "description": "Could not parse AI response properly"
                    }
                ],
                "total_defects": 1
            }
        
        # Create analysis result
        defects = [
            DefectResult(**defect) for defect in analysis_data.get("defects_found", [])
        ]
        
        analysis = AnalysisResult(
            filename=file.filename,
            total_defects=analysis_data.get("total_defects", len(defects)),
            defects_found=defects,
            image_base64=base64_image
        )
        
        # Save to database
        analysis_dict = analysis.model_dump()
        analysis_dict["upload_time"] = analysis.upload_time.isoformat()
        await db.analyses.insert_one(analysis_dict)
        
        return AnalysisResponse(
            success=True,
            message=f"Analysis complete. Found {analysis.total_defects} defects.",
            analysis=analysis
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get("/api/history", response_model=List[AnalysisResult])
async def get_analysis_history(limit: int = 10):
    try:
        cursor = db.analyses.find().sort("upload_time", -1).limit(limit)
        analyses = await cursor.to_list(length=limit)
        
        result = []
        for analysis in analyses:
            # Convert back from ISO format
            if isinstance(analysis.get("upload_time"), str):
                analysis["upload_time"] = datetime.fromisoformat(analysis["upload_time"])
            result.append(AnalysisResult(**analysis))
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")

@app.get("/api/analysis/{analysis_id}", response_model=AnalysisResult)
async def get_analysis(analysis_id: str):
    try:
        analysis = await db.analyses.find_one({"id": analysis_id})
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
            
        # Convert back from ISO format
        if isinstance(analysis.get("upload_time"), str):
            analysis["upload_time"] = datetime.fromisoformat(analysis["upload_time"])
            
        return AnalysisResult(**analysis)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch analysis: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)