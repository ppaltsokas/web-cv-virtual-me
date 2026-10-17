export enum MessageSender {
  User = 'user',
  AI = 'ai'
}

export interface ChatMessage {
  id: string;
  text: string;
  sender: MessageSender;
  timestamp: Date;
  images?: string[]; // Array of image filenames
}

export interface Experience {
  id: string;
  role: string;
  company: string;
  period: string;
  description: string;
  technologies: string[];
}

export interface Education {
  id: string;
  degree: string;
  school: string;
  year: string;
  grade?: string;
}

export interface Certification {
  id: string;
  title: string;
  issuer: string;
  year: string;
  icon?: string; // Icon URL or image path for the certification logo
  credentialUrl?: string; // URL to the certificate image/document
}

export interface Project {
  id: string;
  title: string;
  description: string;
  link?: string;
  technologies: string[];
  pdfPath?: string; // Path to PDF file in knowledge base
}

export interface SkillCategory {
  name: string;
  skills: string[];
}

export interface PersonalInfo {
  name: string;
  title: string;
  bio: string;
  email: string;
  location: string;
  socials: {
    github?: string;
    linkedin?: string;
    twitter?: string;
  };
}

export interface ResumeData {
  personalInfo: PersonalInfo;
  experience: Experience[];
  education: Education[];
  certifications?: Certification[];
  latestProjects?: Project[];
  projects: Project[];
  skills: SkillCategory[];
}
