/** Card data for the Ideas column — driven by ideas table rows (status=new). */
export interface IdeaEntry {
  id: string;
  title: string;
  body: string | null;
  idea_type: string | null;
  opportunity_score: number | null;
  outlier_score: number | null;
  rationale: string | null;
  source_type: string;
  position: number | null;
  created_at: string;
  archived: boolean;
}

/** Card data for the In Progress column — driven by studio_sessions (status=active). */
export interface InProgressEntry {
  session_id: string;
  idea_id: string;
  title: string;
  idea_type: string | null;
  brand_color: string | null;
  brand_id: string | null;
  updated_at: string;
  has_script: boolean;
  has_outline: boolean;
  has_scene: boolean;
  has_thumbnail: boolean;
}

/** Card data for the Ready to Record column — sessions (status=completed) with scene. */
export interface ReadyEntry {
  session_id: string;
  idea_id: string;
  title: string;
  idea_type: string | null;
  target_duration_min: number | null;
  thumbnail_url: string | null;
  output_type: string | null;
  excalidraw_url: string | null;
}

/** Card data for the Published column — driven by yt_metrics table. */
export interface PublishedEntry {
  id: string;
  video_id: string;
  title: string;
  thumbnail_url: string | null;
  views: number | null;
  ctr: number | null;
  watch_time_hrs: number | null;
  avg_duration_s: number | null;
  total_duration_s: number | null;
  subscribers_gained: number | null;
  outlier_score: number | null;
  what_worked: string | null;
  published_at: string | null;
}

export interface ChannelSummary {
  total_views_month: number | null;
  best_video_title: string | null;
  avg_ctr: number | null;
  avg_outlier_score: number | null;
  total_videos: number;
}

export interface KanbanData {
  ideas: IdeaEntry[];
  in_progress: InProgressEntry[];
  ready: ReadyEntry[];
  published: PublishedEntry[];
  channel_summary: ChannelSummary | null;
  youtube_connected: boolean;
}

export interface WeeklySuggestion {
  id: string;
  week_start: string;
  ideas: Array<{
    title: string;
    rationale: string | null;
    opportunity_score: number | null;
    why_now: string | null;
    idea_type: string | null;
    suggested_tags: string[];
  }>;
  dismissed: boolean;
  generated_at: string | null;
}
