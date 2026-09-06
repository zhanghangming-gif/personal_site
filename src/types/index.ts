export type SkillLevel = '熟悉' | '使用过' | '正在学习';

export interface Skill {
  name: string;
  category: string;
  level: SkillLevel;
}
export interface Project {
  id: string;
  title: string;
  type: string;
  summary: string;
  role: string;
  tech: string[];
  status: string;
  github?: string;
  demo?: string;
  cover?: string;
  coverContain?: boolean;
  photos?: CampusPhoto[];
  galleryTitle?: string;
  galleryDescription?: string;
  videos?: ProjectVideo[];
  featured: boolean;
  background: string;
  goal: string;
  solution: string;
  architecture: string[];
  workflow: string[];
  challenge: string;
  result: string;
}
export interface Experience {
  id?: string;
  period: string;
  organization: string;
  role: string;
  work: string;
  growth: string;
}
export interface Honor {
  title: string;
  level: string;
  description: string;
  year: string;
  category: string;
  image: string;
}
export interface CampusPhoto {
  src: string;
  alt: string;
  caption: string;
  contain?: boolean;
}
export interface ProjectVideo {
  src: string;
  title: string;
  caption: string;
  poster?: string;
}
export interface Message {
  id: string;
  nickname: string;
  content: string;
  createdAt: string;
  likeCount: number;
  liked: boolean;
  replies: MessageReply[];
  pinned?: boolean;
  emailVerified?: boolean;
}
export interface MessageReply {
  id: string;
  nickname: string;
  content: string;
  createdAt: string;
  likeCount: number;
  liked: boolean;
}
export interface MessagePage {
  items: Message[];
  page: number;
  pageSize: number;
  total: number;
}
export interface MessagePayload {
  nickname: string;
  email?: string;
  content: string;
  website: string;
  visitorId?: string;
}
export interface ReplyPayload {
  nickname: string;
  content: string;
  website: string;
}
export interface LikeResult {
  liked: boolean;
  likeCount: number;
}
export interface StarState {
  starred: boolean;
  starCount: number;
}
export interface GuestIdentity {
  nickname: string;
  email: string;
  verified: boolean;
  remember: boolean;
}
