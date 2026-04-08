import client from "./client";

export interface BlogPost {
  id: string;
  slug: string;
  title: string;
  subtitle: string | null;
  content: string;
  excerpt: string | null;
  cover_image_url: string | null;
  meta_title: string | null;
  meta_description: string | null;
  og_image_url: string | null;
  author_name: string;
  tags: string[];
  status: string;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface BlogListResponse {
  posts: BlogPost[];
  total: number;
  page: number;
  per_page: number;
}

// Public
export const getPublishedPosts = (page = 1, tag?: string) =>
  client.get<BlogListResponse>("/blog/posts", { params: { page, tag } });

export const getPublishedPost = (slug: string) =>
  client.get<BlogPost>(`/blog/posts/${slug}`);

// Admin
export const adminListPosts = (page = 1, status?: string) =>
  client.get<BlogListResponse>("/admin/blog", { params: { page, status } });

export const adminGetPost = (id: string) =>
  client.get<BlogPost>(`/admin/blog/${id}`);

export const adminCreatePost = (data: Partial<BlogPost>) =>
  client.post<BlogPost>("/admin/blog", data);

export const adminUpdatePost = (id: string, data: Partial<BlogPost>) =>
  client.put<BlogPost>(`/admin/blog/${id}`, data);

export const adminDeletePost = (id: string) =>
  client.delete(`/admin/blog/${id}`);
