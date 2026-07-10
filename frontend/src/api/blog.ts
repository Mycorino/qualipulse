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

// NOTE: no admin helpers here on purpose. /admin/blog/* needs the admin
// Bearer key, not the researcher JWT this shared client injects —
// AdminBlog.tsx builds its own client with the right credentials.
