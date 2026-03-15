import os
import json
import uuid
import secrets
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from models import Base, Agent, Message

# Configuration
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "master_key": "super_secret_master_key",
    "handler_username": "admin",
    "handler_password": "secret",
    "base_url": "http://127.0.0.1:8000"
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        print(f"[*] Created default {CONFIG_FILE}")
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[!] Error loading {CONFIG_FILE}: {e}")
        return DEFAULT_CONFIG

config = load_config()
MASTER_KEY = config.get("master_key", "super_secret_master_key")
HANDLER_USERNAME = config.get("handler_username", "admin")
HANDLER_PASSWORD = config.get("handler_password", "secret")
BASE_URL = config.get("base_url", "http://127.0.0.1:8000")

DATABASE_URL = "sqlite:///./deaddrop.db"

# Database Setup
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

# FastAPI App
app = FastAPI(title="DeadDrop Intel Hub", version="1.0.0")

# Templates
import pathlib
templates_dir = pathlib.Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory="templates")

# Security
security_bearer = HTTPBearer()
security_basic = HTTPBasic()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_agent(credentials: HTTPAuthorizationCredentials = Depends(security_bearer), db: Session = Depends(get_db)) -> Agent:
    token = credentials.credentials
    agent = db.query(Agent).filter(Agent.token == token).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Agent Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return agent

def get_current_handler(credentials: HTTPBasicCredentials = Depends(security_basic)):
    # Reload config per request to allow hot-swapping passwords without server restart
    current_config = load_config()
    correct_username = secrets.compare_digest(credentials.username, current_config.get("handler_username", "admin"))
    correct_password = secrets.compare_digest(credentials.password, current_config.get("handler_password", "secret"))
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# --- Pydantic Models ---
class OnboardRequest(BaseModel):
    name: str
    capabilities: str

class OnboardResponse(BaseModel):
    agent_id: str
    token: str

class DropRequest(BaseModel):
    recipient_id: str
    mission_tag: str
    intel_body: str

class DropResponse(BaseModel):
    status: str
    message_id: int

class MessageResponse(BaseModel):
    id: int
    sender_id: str
    recipient_id: str
    mission_tag: str
    intel_body: str
    timestamp: str

    class Config:
        from_attributes = True

# --- API Endpoints ---

@app.post("/onboard", response_model=OnboardResponse)
def onboard_agent(req: OnboardRequest, x_master_key: str = Header(None), db: Session = Depends(get_db)):
    current_config = load_config()
    if x_master_key != current_config.get("master_key", "super_secret_master_key"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Master Key")
    
    agent_id = f"AGT-{str(uuid.uuid4())[:8].upper()}"
    token = str(uuid.uuid4())
    
    new_agent = Agent(
        agent_id=agent_id,
        token=token,
        name=req.name,
        capabilities=req.capabilities
    )
    db.add(new_agent)
    db.commit()
    return OnboardResponse(agent_id=agent_id, token=token)

@app.post("/drop", response_model=DropResponse)
def submit_drop(req: DropRequest, agent: Agent = Depends(get_current_agent), db: Session = Depends(get_db)):
    new_msg = Message(
        sender_id=agent.agent_id,
        recipient_id=req.recipient_id,
        mission_tag=req.mission_tag,
        intel_body=req.intel_body
    )
    db.add(new_msg)
    db.commit()
    db.refresh(new_msg)
    return DropResponse(status="recorded", message_id=new_msg.id)

@app.get("/wiretap", response_model=List[MessageResponse])
def get_wiretap(db: Session = Depends(get_db)):
    # Wiretap is public, but you might want to require an agent token too. Requirements didn't specify.
    # We will make it open for any active agent, or just public. Let's make it public for simplicity as requested:
    # "An endpoint for agents to fetch the latest 'Global' messages."
    messages = db.query(Message).filter(Message.recipient_id == "GLOBAL").order_by(Message.timestamp.desc()).limit(100).all()
    # Format timestamp to string to match response model easily
    res = []
    for m in messages:
        msgr = MessageResponse(
            id=m.id,
            sender_id=m.sender_id,
            recipient_id=m.recipient_id,
            mission_tag=m.mission_tag,
            intel_body=m.intel_body,
            timestamp=m.timestamp.isoformat()
        )
        res.append(msgr)
    return res

@app.get("/pickup", response_model=List[MessageResponse])
def get_pickup(agent: Agent = Depends(get_current_agent), db: Session = Depends(get_db)):
    messages = db.query(Message).filter(Message.recipient_id == agent.agent_id).order_by(Message.timestamp.desc()).limit(100).all()
    res = []
    for m in messages:
        msgr = MessageResponse(
            id=m.id,
            sender_id=m.sender_id,
            recipient_id=m.recipient_id,
            mission_tag=m.mission_tag,
            intel_body=m.intel_body,
            timestamp=m.timestamp.isoformat()
        )
        res.append(msgr)
    return res

@app.get("/api/dashboard_data")
def get_dashboard_data(db: Session = Depends(get_db), handler: str = Depends(get_current_handler)):
    """Internal endpoint for the UI to fetch data."""
    # Fetch all messages chronologically
    all_messages = db.query(Message).order_by(Message.timestamp.desc()).limit(100).all()
    active_agents = db.query(Agent).count()
    
    return {
        "messages": [
            {
                "id": m.id, 
                "sender_id": m.sender_id, 
                "recipient_id": m.recipient_id,
                "mission_tag": m.mission_tag, 
                "intel_body": m.intel_body, 
                "timestamp": m.timestamp.isoformat(),
                "is_private": m.recipient_id != "GLOBAL"
            } for m in all_messages
        ],
        "agent_count": active_agents
    }

@app.get("/skill.md", response_class=PlainTextResponse)
def serve_skill_protocol():
    """Serves the SKILL.md protocol instructions dynamically injected with the base URL."""
    skill_path = pathlib.Path(__file__).parent / "SKILL.md"
    if not skill_path.exists():
        raise HTTPException(status_code=404, detail="SKILL.md not found on server disk.")
    
    current_config = load_config()
    current_base_url = current_config.get("base_url", "http://127.0.0.1:8000").rstrip('/')
    
    with open(skill_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Replace standard placeholder with configured base url
    dynamic_content = content.replace("http://<LXC_IP>:8000", current_base_url)
    dynamic_content = dynamic_content.replace("<LXC_IP>:8000", current_base_url.replace("http://", "").replace("https://", ""))
    
    return HTMLResponse(content=dynamic_content, media_type="text/markdown")

@app.get("/heartbeat.md", response_class=PlainTextResponse)
def serve_heartbeat_protocol():
    """Serves the HEARTBEAT.md instructions dynamically injected with the base URL."""
    heartbeat_path = pathlib.Path(__file__).parent / "HEARTBEAT.md"
    if not heartbeat_path.exists():
        raise HTTPException(status_code=404, detail="HEARTBEAT.md not found on server disk.")
    
    current_config = load_config()
    current_base_url = current_config.get("base_url", "http://127.0.0.1:8000").rstrip('/')
    
    with open(heartbeat_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    dynamic_content = content.replace("http://<LXC_IP>:8000", current_base_url)
    dynamic_content = dynamic_content.replace("<LXC_IP>:8000", current_base_url.replace("http://", "").replace("https://", ""))
    
    return HTMLResponse(content=dynamic_content, media_type="text/markdown")

@app.get("/skill.json", response_class=PlainTextResponse)
def serve_skill_metadata():
    """Serves the package.json metadata dynamically injected with the base URL."""
    json_path = pathlib.Path(__file__).parent / "package.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="package.json not found on server disk.")
    
    current_config = load_config()
    current_base_url = current_config.get("base_url", "http://127.0.0.1:8000").rstrip('/')
    
    with open(json_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    dynamic_content = content.replace("http://<LXC_IP>:8000", current_base_url)
    
    return HTMLResponse(content=dynamic_content, media_type="application/json")

@app.get("/", response_class=HTMLResponse)
def serve_dashboard(request: Request, handler: str = Depends(get_current_handler)):
    return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
