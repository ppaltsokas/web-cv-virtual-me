/// <reference types="vite/client" />
declare module 'virtual:portfolio-profile' {
  const profile: {
    resume: import('./types').ResumeData;
    chat: { name: string; greeting: string; placeholder: string; avatar: string };
    cvAvailable: boolean;
  };
  export default profile;
}
