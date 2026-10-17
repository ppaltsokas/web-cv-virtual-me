"""Validated owner configuration, independent of any particular portfolio."""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

def validate_url(value: str, local: bool = False) -> str:
    if not value:
        return value
    parsed = urlparse(value)
    if local and value.startswith('/') and not value.startswith('//') and not parsed.scheme and not parsed.netloc and '..' not in value.split('/') and '\\' not in value:
        return value
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use an absolute HTTPS URL or an allowed local asset path')
    return value

class Socials(StrictModel):
    github: str = ''
    linkedin: str = ''
    twitter: str = ''
    _urls = field_validator('github', 'linkedin', 'twitter')(validate_url)

class PersonalInfo(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    bio: str = Field(default='', max_length=6000)
    email: str = Field(default='', max_length=254)
    location: str = Field(default='', max_length=200)
    socials: Socials = Field(default_factory=Socials)

class Experience(StrictModel):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    role: str
    company: str
    period: str
    description: str
    technologies: list[str] = Field(default_factory=list)

class Education(StrictModel):
    id: str
    degree: str
    school: str
    year: str
    grade: str = ''

class Certification(StrictModel):
    id: str
    title: str
    issuer: str
    year: str
    icon: str = ''
    credentialUrl: str = ''
    _credential = field_validator('credentialUrl')(validate_url)
    @field_validator('icon')
    @classmethod
    def icon_url(cls, value):
        return validate_url(value, local=True)

class Project(StrictModel):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    title: str
    description: str
    technologies: list[str] = Field(default_factory=list)
    link: str = ''
    pdfPath: str = Field(default='', pattern=r'^[A-Za-z0-9_-]{0,80}$')
    _url = field_validator('link')(validate_url)

class SkillCategory(StrictModel):
    name: str
    skills: list[str]

class Resume(StrictModel):
    personalInfo: PersonalInfo
    experience: list[Experience] = Field(default_factory=list, max_length=30)
    education: list[Education] = Field(default_factory=list, max_length=30)
    certifications: list[Certification] = Field(default_factory=list, max_length=30)
    latestProjects: list[Project] = Field(default_factory=list, max_length=50)
    projects: list[Project] = Field(default_factory=list, max_length=50)
    skills: list[SkillCategory] = Field(default_factory=list, max_length=30)

class Chat(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    greeting: str = Field(max_length=1500)
    placeholder: str = Field(default='Ask about my work...', max_length=200)
    avatar: str = '/avatar.svg'
    voice: str = Field(default='Warm, clear, concise and candid.', max_length=1500)
    @field_validator('avatar')
    @classmethod
    def avatar_url(cls, value):
        return validate_url(value, local=True)

class Entrance(StrictModel):
    title: str = Field(default="Welcome to {name}'s Web CV", max_length=240)
    subtitle: str = Field(default='and the Virtual-Me Chatbot', max_length=240)

class Site(StrictModel):
    title: str = Field(default='{name} | Web CV', max_length=240)
    description: str = Field(default="Explore {name}'s experience and projects.", max_length=600)
    url: str = ''
    _url = field_validator('url')(validate_url)

class Profile(StrictModel):
    timezone: str = 'UTC'
    resume: Resume
    chat: Chat
    entrance: Entrance = Field(default_factory=Entrance)
    site: Site = Field(default_factory=Site)
    birthMonthYear: str = Field(default='', max_length=30)
    @model_validator(mode='after')
    def bounded_profile(self):
        if len(self.evidence()) > 20000:
            raise ValueError('Profile evidence exceeds 20,000 characters; move detailed material into documents')
        return self
    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        ZoneInfo(value)
        return value

    def evidence(self) -> str:
        data = self.resume.model_dump()
        if self.birthMonthYear:
            data['verified_birth_month_year'] = self.birthMonthYear
        return json.dumps(data, ensure_ascii=False)

class DocumentSpec(StrictModel):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    label: str = Field(min_length=1, max_length=160)
    path: str
    kind: Literal['cv', 'summary', 'document'] = 'document'
    public: bool = False

class Manifest(StrictModel):
    documents: list[DocumentSpec] = Field(default_factory=list, max_length=50)
    @field_validator('documents')
    @classmethod
    def unique_documents(cls, documents):
        ids = [document.id for document in documents]
        labels = [document.label.casefold() for document in documents]
        if len(ids) != len(set(ids)) or len(labels) != len(set(labels)) or 'portfolio profile' in labels or sum(document.kind == 'cv' for document in documents) > 1:
            raise ValueError('Document IDs and source labels must be unique; Portfolio profile is reserved; at most one CV is allowed')
        return documents

def config_path(kind: str, root: Path = ROOT) -> Path:
    variable = {'profile': 'PORTFOLIO_PROFILE', 'content': 'CONTENT_MANIFEST'}[kind]
    if os.getenv(variable):
        return (root / os.environ[variable]).resolve()
    local = root / 'config' / f'{kind}.local.json'
    return local if local.is_file() else root / 'config' / f'{kind}.example.json'

def load_profile(path: Path | None = None) -> Profile:
    return Profile.model_validate_json((path or config_path('profile')).read_text(encoding='utf-8-sig'))

def load_manifest(path: Path | None = None) -> Manifest:
    return Manifest.model_validate_json((path or config_path('content')).read_text(encoding='utf-8-sig'))

def document_path(root: Path, spec: DocumentSpec) -> Path:
    path = (root / spec.path).resolve()
    if not path.is_relative_to(root.resolve()) or path.suffix.lower() not in {'.pdf', '.md', '.txt'}:
        raise ValueError(f'Invalid document path for {spec.id}')
    if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError(f'Document missing or larger than 20 MiB: {spec.id}')
    return path
