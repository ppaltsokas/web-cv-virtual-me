import React, { useState, useEffect } from 'react';
import {
  Github,
  Linkedin,
  Twitter,
  Mail,
  MapPin,
  ExternalLink,
  Briefcase,
  Code,
  Cpu,
  MessageSquare,
  Download,
  GraduationCap,
  Award,
  FileText,
  X
} from 'lucide-react';
import { RESUME_DATA, API_URL, CHAT_CONFIG, CV_AVAILABLE } from './constants';
import ChatInterface from './components/ChatInterface';
import ProjectCard from './components/ProjectCard';

const App: React.FC = () => {
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [selectedCredential, setSelectedCredential] = useState<string | null>(null);
  const { personalInfo, experience, education, certifications, latestProjects, projects, skills } = RESUME_DATA;

  // Responsive layout detection
  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 1024);
    checkMobile();
    window.addEventListener('resize', checkMobile);

    // Auto-open chat on desktop
    if (window.innerWidth >= 1024) {
        const timer = setTimeout(() => setIsChatOpen(true), 1500);
        return () => clearTimeout(timer);
    }

    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const toggleChat = () => setIsChatOpen(!isChatOpen);

  // Helper function to check if URL is an image or HTML page
  const isImageUrl = (url: string): boolean => {
    // Check for image file extensions
    const imageExtensions = /\.(jpg|jpeg|png|gif|webp|svg)(\?|$)/i;
    if (imageExtensions.test(url)) {
      return true;
    }

    return false;
  };

  // Handle credential click - open in modal if image, new tab if HTML
  const handleCredentialClick = (url: string) => {
    if (isImageUrl(url)) {
      setSelectedCredential(url);
    } else {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  };

  // Close modal on ESC key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && selectedCredential) {
        setSelectedCredential(null);
      }
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [selectedCredential]);

  return (
    <div className="min-h-screen bg-slate-950 selection:bg-indigo-500/30">
      {/* Decorative Background Elements */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl -translate-y-1/2"></div>
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl translate-y-1/2"></div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 relative z-10">

        {/* Header / Hero Section */}
        <header className="mb-16 text-center lg:text-left lg:flex lg:items-end lg:justify-between border-b border-slate-800 pb-12 animate-fade-in-up">
          <div className="space-y-6">
            <div className="space-y-2">
              <h1 className="text-5xl sm:text-6xl font-bold text-slate-100 tracking-tight">
                {personalInfo.name}
              </h1>
              <p className="text-xl sm:text-2xl text-slate-400 font-light">
                {personalInfo.title}
              </p>
            </div>

            <p className="max-w-2xl text-slate-400 leading-relaxed text-justify">
              {personalInfo.bio}
            </p>

            <div className="flex flex-wrap gap-4 justify-center lg:justify-start pt-2">
              {personalInfo.email && <a href={`mailto:${personalInfo.email}`} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 transition-all text-sm">
                <Mail size={16} /> {personalInfo.email}
              </a>}
              {personalInfo.location && <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800/50 border border-slate-700/50 text-slate-400 text-sm">
                <MapPin size={16} /> {personalInfo.location}
              </div>}
            </div>

            <div className="flex gap-4 justify-center lg:justify-start">
                {personalInfo.socials.github && (
                   <a href={personalInfo.socials.github} target="_blank" rel="noreferrer" className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-full transition-all">
                       <Github size={24} />
                   </a>
                )}
                {personalInfo.socials.linkedin && (
                   <a href={personalInfo.socials.linkedin} target="_blank" rel="noreferrer" className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-full transition-all">
                       <Linkedin size={24} />
                   </a>
                )}
                 {personalInfo.socials.twitter && (
                   <a href={personalInfo.socials.twitter} target="_blank" rel="noreferrer" className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-full transition-all">
                       <Twitter size={24} />
                   </a>
                )}
            </div>
          </div>

          {CV_AVAILABLE && <div className="mt-8 lg:mt-0">
             <a
                href={`${API_URL}/me/cv`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-6 py-3 bg-slate-100 text-slate-900 font-semibold rounded-xl hover:bg-white transition-all shadow-lg shadow-white/5 active:scale-95"
             >
               <Download size={18} />
               Download Resume
             </a>
          </div>}
        </header>

        <main className="grid grid-cols-1 lg:grid-cols-3 gap-12">

          {/* Left Column (Main Content) */}
          <div className="lg:col-span-2 space-y-16">

            {/* Experience Section */}
            {experience.length > 0 && (<>
            <section className="animate-fade-in-up" style={{ animationDelay: '100ms' }}>
              <h2 className="flex items-center gap-3 text-2xl font-bold text-slate-100 mb-8">
                <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
                  <Briefcase size={24} />
                </div>
                Experience
              </h2>
              <div className="space-y-8 border-l-2 border-slate-800 pl-8 ml-4">
                {experience.map((job) => (
                  <div key={job.id} className="relative group">
                    <div className="absolute -left-[41px] top-1 w-5 h-5 rounded-full border-4 border-slate-950 bg-indigo-500 group-hover:scale-125 transition-transform"></div>
                    <div className="space-y-2">
                      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
                        <h3 className="text-xl font-semibold text-slate-200">{job.role}</h3>
                        <span className="text-sm font-mono text-slate-500 bg-slate-900 px-2 py-1 rounded border border-slate-800">
                          {job.period}
                        </span>
                      </div>
                      <div className="text-indigo-400 font-medium">{job.company}</div>
                      <p className="text-slate-400 leading-relaxed whitespace-pre-line">{job.description}</p>
                      <div className="flex flex-wrap gap-2 pt-2">
                        {job.technologies.map((tech) => (
                          <span key={tech} className="px-2 py-1 text-xs rounded bg-slate-800 text-slate-300 border border-slate-700">
                            {tech}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section></>)}

            {/* Education Section */}
            {education.length > 0 && (<>
            <section className="animate-fade-in-up" style={{ animationDelay: '200ms' }}>
              <h2 className="flex items-center gap-3 text-2xl font-bold text-slate-100 mb-8">
                <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400">
                  <GraduationCap size={24} />
                </div>
                Education
              </h2>
              <div className="grid gap-6">
                {education.map((edu) => (
                   <div key={edu.id} className="p-6 rounded-2xl bg-slate-900/30 border border-slate-800 flex flex-col sm:flex-row justify-between sm:items-center gap-4">
                      <div>
                         <h3 className="text-lg font-bold text-slate-200">{edu.degree}</h3>
                         <div className="text-slate-400">{edu.school}</div>
                      </div>
                      <div className="text-right flex flex-col items-end">
                         <span className="text-sm font-mono text-slate-500 bg-slate-900 px-2 py-1 rounded border border-slate-800 mb-1">
                           {edu.year}
                         </span>
                         {edu.grade && <span className="text-xs text-indigo-400 font-medium">Grade: {edu.grade}</span>}
                      </div>
                   </div>
                ))}
              </div>
            </section></>)}

            {/* Certifications Section */}
            {certifications && certifications.length > 0 && (
              <section className="animate-fade-in-up" style={{ animationDelay: '250ms' }}>
                <h2 className="flex items-center gap-3 text-2xl font-bold text-slate-100 mb-8">
                  <div className="p-2 rounded-lg bg-yellow-500/10 text-yellow-400">
                    <Award size={24} />
                  </div>
                  Certifications
                </h2>
                <div className="grid gap-4">
                  {certifications.map((cert) => (
                    <div key={cert.id} className="p-5 rounded-2xl bg-slate-900/30 border border-slate-800 flex items-start gap-4 hover:border-yellow-500/50 transition-colors">
                      {cert.icon && (
                        <div className="flex-shrink-0 w-12 h-12 flex items-center justify-center bg-white rounded-lg p-2 border border-slate-700">
                          {cert.icon.startsWith('/') || cert.icon.startsWith('http') ? (
                            <img
                              src={cert.icon}
                              alt={`${cert.issuer} logo`}
                              className="w-full h-full object-contain"
                              onError={(e) => {
                                // Replace with fallback icon if image fails
                                const target = e.target as HTMLImageElement;
                                target.style.display = 'none';
                                if (!target.parentElement?.querySelector('.icon-fallback')) {
                                  const fallback = document.createElement('div');
                                  fallback.className = 'icon-fallback text-xl';
                                  fallback.textContent = '🏆';
                                  target.parentElement?.appendChild(fallback);
                                }
                              }}
                            />
                          ) : (
                            <div className="text-2xl">{cert.icon}</div>
                          )}
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1">
                            <h3 className="text-lg font-bold text-slate-200 mb-1">{cert.title}</h3>
                            <div className="flex flex-wrap items-center gap-2 text-sm">
                              <span className="text-slate-400">{cert.issuer}</span>
                              <span className="text-slate-600">•</span>
                              <span className="text-slate-500 font-mono">{cert.year}</span>
                            </div>
                          </div>
                          {cert.credentialUrl && (
                            cert.credentialUrl.includes('udemy.com/course/') ? (
                              <a
                                href={cert.credentialUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="flex-shrink-0 p-1.5 text-slate-500 hover:text-yellow-400 hover:bg-yellow-500/10 rounded-lg transition-colors"
                                title="View course"
                              >
                                <ExternalLink size={16} />
                              </a>
                            ) : (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleCredentialClick(cert.credentialUrl!);
                                }}
                                className="flex-shrink-0 p-1.5 text-slate-500 hover:text-yellow-400 hover:bg-yellow-500/10 rounded-lg transition-colors"
                                title="Show credential"
                              >
                                <FileText size={16} />
                              </button>
                            )
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Latest Projects Section */}
            {latestProjects && latestProjects.length > 0 && (
              <section className="animate-fade-in-up" style={{ animationDelay: '280ms' }}>
                <h2 className="flex items-center gap-3 text-2xl font-bold text-slate-100 mb-8">
                  <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400">
                    <Code size={24} />
                  </div>
                  Latest Projects
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {latestProjects.map(project => <ProjectCard key={project.id} project={project} />)}
                </div>
              </section>
            )}

            {/* Projects Section */}
            {projects.length > 0 && (<>
            <section className="animate-fade-in-up" style={{ animationDelay: '300ms' }}>
              <h2 className="flex items-center gap-3 text-2xl font-bold text-slate-100 mb-8">
                <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                  <Code size={24} />
                </div>
                Personal Projects
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {projects.map(project => <ProjectCard key={project.id} project={project} />)}
              </div>
            </section></>)}

          </div>

          {/* Right Column (Skills & Tech) */}
          <div className="space-y-12">

            {/* Skills Section */}
            {skills.length > 0 && <section className="animate-fade-in-up" style={{ animationDelay: '400ms' }}>
              <h2 className="flex items-center gap-3 text-2xl font-bold text-slate-100 mb-8">
                <div className="p-2 rounded-lg bg-pink-500/10 text-pink-400">
                  <Cpu size={24} />
                </div>
                Technical Skills
              </h2>
              <div className="space-y-6">
                {skills.map((category) => (
                  <div key={category.name} className="p-6 rounded-2xl bg-slate-900 border border-slate-800">
                    <h3 className="text-lg font-semibold text-slate-300 mb-4 border-b border-slate-800 pb-2">
                      {category.name}
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {category.skills.map((skill) => (
                        <div key={skill} className="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 text-sm hover:bg-slate-700 hover:text-white transition-colors cursor-default">
                          {skill}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>}

            {/* CTA Box */}
            <div className="p-6 rounded-2xl bg-gradient-to-br from-indigo-600 to-purple-700 text-white shadow-xl animate-fade-in-up" style={{ animationDelay: '500ms' }}>
              <h3 className="text-xl font-bold mb-2">Want to chat?</h3>
              <p className="text-indigo-100 mb-4 text-sm">
                Ask my virtual persona about my experience, projects and the decisions behind my work.
              </p>
              <button
                onClick={() => setIsChatOpen(true)}
                className="w-full py-2 px-4 bg-white text-indigo-600 rounded-lg font-semibold hover:bg-indigo-50 transition-colors flex items-center justify-center gap-2"
              >
                <MessageSquare size={18} />
                Chat with {CHAT_CONFIG.name}
              </button>
            </div>

          </div>
        </main>

        <footer className="mt-24 pt-8 border-t border-slate-800 text-center text-slate-500 text-sm">
          <p>© {new Date().getFullYear()} {personalInfo.name}.</p>
        </footer>
      </div>

      {/* Floating Chat Button with Orbiting Stars (Only visible if chat is closed) */}
      <div className={`fixed z-40 bottom-6 right-6 chat-button-container ${isChatOpen ? 'scale-0 opacity-0' : 'scale-100 opacity-100'} transition-all duration-300`}>
        <div className="chat-button-backlight"></div>
        <div className="star-orbit-container">
          <div className="star-orbit" style={{ animationDelay: '0s' }}></div>
          <div className="star-orbit" style={{ animationDelay: '-2s' }}></div>
          <div className="star-orbit" style={{ animationDelay: '-4s' }}></div>
          <div className="star-orbit" style={{ animationDelay: '-6s' }}></div>
          <div className="star-orbit" style={{ animationDelay: '-1s' }}></div>
          <div className="star-orbit" style={{ animationDelay: '-3s' }}></div>
        </div>
        <button
          onClick={toggleChat}
          className="relative z-20 p-4 rounded-full bg-indigo-600 text-white shadow-2xl hover:bg-indigo-500 transition-all duration-300 hover:scale-110 active:scale-95"
          aria-label="Open Chat"
        >
          <MessageSquare size={24} />
        </button>
      </div>

      {/* Certificate Modal */}
      {selectedCredential && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
          onClick={() => setSelectedCredential(null)}
        >
          <div
            className="relative max-w-4xl max-h-[90vh] w-full bg-slate-900 rounded-2xl border border-slate-700 shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close Button */}
            <button
              onClick={() => setSelectedCredential(null)}
              className="absolute top-4 right-4 z-10 p-2 bg-slate-800/80 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-white transition-colors"
              aria-label="Close"
            >
              <X size={20} />
            </button>

            {/* Certificate Image */}
            <div className="overflow-auto max-h-[90vh]">
              <img
                src={selectedCredential}
                alt="Certificate"
                className="w-full h-auto"
                onError={(e) => {
                  const target = e.target as HTMLImageElement;
                  target.style.display = 'none';
                  const errorDiv = target.parentElement?.querySelector('.error-message');
                  if (!errorDiv) {
                    const div = document.createElement('div');
                    div.className = 'error-message p-8 text-center text-slate-400';
                    div.textContent = 'Failed to load certificate image.';
                    target.parentElement?.appendChild(div);
                  }
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Chat Interface */}
      <ChatInterface
        isOpen={isChatOpen}
        onClose={() => setIsChatOpen(false)}
        isMobile={isMobile}
      />
    </div>
  );
};

export default App;
