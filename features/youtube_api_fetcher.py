"""
features/youtube_api_fetcher.py
YouTube Analytics Fetcher
Fetches real video metrics from YouTube API using teacher's credentials.
"""

import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class YouTubeAPIFetcher:
    """Fetches video metrics from YouTube API."""

    def __init__(self, oauth_manager):
        """
        Args:
            oauth_manager: YouTubeOAuthManager instance
        """
        self.oauth_manager = oauth_manager

    def fetch_video_metrics(self, teacher_id: str, video_id: str) -> dict or None:
        """
        Fetch metrics for a specific YouTube video.
        
        Args:
            teacher_id: UUID of teacher (to get their credentials)
            video_id: YouTube video ID (from video URL)
        
        Returns:
            Dict with {views, likes, comments, shares} or None on error
        """
        # Get teacher's YouTube credentials
        credentials = self.oauth_manager.get_credentials(teacher_id)
        if not credentials:
            logger.error(f"No YouTube credentials for teacher {teacher_id}")
            return None

        try:
            # Build YouTube API client
            youtube = build('youtube', 'v3', credentials=credentials)
            
            # Fetch video statistics
            request = youtube.videos().list(
                part='statistics',
                id=video_id
            )
            
            response = request.execute()
            
            if not response.get('items'):
                logger.warning(f"Video {video_id} not found for teacher {teacher_id}")
                return None
            
            stats = response['items'][0]['statistics']
            
            return {
                'views': int(stats.get('viewCount', 0)),
                'likes': int(stats.get('likeCount', 0)),
                'comments': int(stats.get('commentCount', 0)),
                'shares': 0  # YouTube API doesn't expose shares directly
            }

        except HttpError as e:
            logger.error(f"YouTube API error for teacher {teacher_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Fetch video metrics error: {e}")
            return None

    def fetch_channel_videos(self, teacher_id: str, channel_id: str, max_results: int = 50) -> list or None:
        """
        Fetch all uploaded videos for a teacher's channel.
        
        Args:
            teacher_id: UUID of teacher
            channel_id: YouTube channel ID
            max_results: Max videos to return
        
        Returns:
            List of dicts with {video_id, title, published_at, views, likes, comments} or None
        """
        credentials = self.oauth_manager.get_credentials(teacher_id)
        if not credentials:
            logger.error(f"No YouTube credentials for teacher {teacher_id}")
            return None

        try:
            youtube = build('youtube', 'v3', credentials=credentials)
            
            # Get uploads playlist ID for the channel
            channel_request = youtube.channels().list(
                part='contentDetails',
                id=channel_id
            )
            channel_response = channel_request.execute()
            
            if not channel_response.get('items'):
                logger.warning(f"Channel {channel_id} not found")
                return None
            
            uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            
            # Get videos from uploads playlist
            playlist_request = youtube.playlistItems().list(
                part='snippet,contentDetails',
                playlistId=uploads_playlist_id,
                maxResults=min(max_results, 50),
                order='date'
            )
            
            playlist_response = playlist_request.execute()
            
            videos = []
            video_ids = []
            
            # Extract video IDs and basic info
            for item in playlist_response.get('items', []):
                video_id = item['contentDetails']['videoId']
                video_ids.append(video_id)
                
                videos.append({
                    'video_id': video_id,
                    'title': item['snippet']['title'],
                    'published_at': item['snippet']['publishedAt'],
                    'description': item['snippet']['description'][:500] if item['snippet'].get('description') else '',
                })
            
            # Fetch statistics for all videos
            if video_ids:
                stats_request = youtube.videos().list(
                    part='statistics',
                    id=','.join(video_ids)
                )
                stats_response = stats_request.execute()
                
                # Map statistics to videos
                stats_by_id = {}
                for item in stats_response.get('items', []):
                    stats_by_id[item['id']] = item['statistics']
                
                for video in videos:
                    stats = stats_by_id.get(video['video_id'], {})
                    video['views'] = int(stats.get('viewCount', 0))
                    video['likes'] = int(stats.get('likeCount', 0))
                    video['comments'] = int(stats.get('commentCount', 0))
            
            logger.info(f"Fetched {len(videos)} videos for channel {channel_id}")
            return videos

        except HttpError as e:
            logger.error(f"YouTube API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Fetch channel videos error: {e}")
            return None

    def fetch_channel_subscribers(self, teacher_id: str, channel_id: str) -> int or None:
        """
        Fetch channel subscriber count.
        
        Args:
            teacher_id: UUID of teacher
            channel_id: YouTube channel ID
        
        Returns:
            Subscriber count or None on error
        """
        credentials = self.oauth_manager.get_credentials(teacher_id)
        if not credentials:
            logger.error(f"No YouTube credentials for teacher {teacher_id}")
            return None

        try:
            youtube = build('youtube', 'v3', credentials=credentials)
            
            request = youtube.channels().list(
                part='statistics',
                id=channel_id
            )
            
            response = request.execute()
            
            if not response.get('items'):
                logger.warning(f"Channel {channel_id} not found")
                return None
            
            stats = response['items'][0]['statistics']
            subs = int(stats.get('subscriberCount', 0))
            
            logger.info(f"Channel {channel_id} has {subs} subscribers")
            return subs

        except HttpError as e:
            logger.error(f"YouTube API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Fetch subscribers error: {e}")
            return None
