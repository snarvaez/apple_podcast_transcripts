#!/usr/bin/env python3
"""
Podcast Transcript Downloader
Downloads transcripts for Apple Podcast episodes when available.
Note: Transcript availability varies by podcast and platform.
"""

import requests
import json
import time
import os
from urllib.parse import urlparse, parse_qs
import re
from datetime import datetime

class PodcastTranscriptDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    def extract_podcast_id(self, apple_podcast_url):
        """Extract podcast ID from Apple Podcasts URL"""
        # Apple Podcasts URL format: https://podcasts.apple.com/us/podcast/name/id123456789
        match = re.search(r'/id(\d+)', apple_podcast_url)
        if match:
            return match.group(1)
        return None
    
    def get_podcast_info(self, podcast_id):
        """Get podcast information from iTunes API"""
        url = f"https://itunes.apple.com/lookup?id={podcast_id}&entity=podcast"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            
            if data['resultCount'] > 0:
                return data['results'][0]
            return None
        except Exception as e:
            print(f"Error fetching podcast info: {e}")
            return None
    
    def get_rss_feed(self, feed_url):
        """Parse RSS feed to get episode information"""
        try:
            import feedparser
            print(f"Fetching RSS feed: {feed_url}")
            
            # First try to fetch the RSS feed directly
            response = self.session.get(feed_url)
            print(f"RSS feed HTTP status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"Failed to fetch RSS feed. Status code: {response.status_code}")
                print(f"Response content: {response.text[:500]}...")
                return None
            
            feed = feedparser.parse(response.content)
            
            # Debug information
            print(f"Feed parsed successfully")
            print(f"Feed title: {feed.feed.get('title', 'Unknown')}")
            print(f"Feed description: {feed.feed.get('description', 'Unknown')[:100]}...")
            print(f"Number of entries found: {len(feed.entries)}")
            
            if len(feed.entries) == 0:
                print("No entries found in feed. This could mean:")
                print("1. The RSS feed is empty or inactive")
                print("2. The RSS feed URL is incorrect")
                print("3. The feed format is not standard")
                print(f"Feed keys: {list(feed.feed.keys())}")
            
            return feed
        except ImportError:
            print("feedparser not installed. Install with: pip install feedparser")
            return None
        except Exception as e:
            print(f"Error parsing RSS feed: {e}")
            return None
    
    def check_transcript_availability(self, episode_url):
        """Check if transcript is available for an episode"""
        # This is a simplified check - actual implementation would depend on
        # the specific podcast platform's transcript availability
        try:
            response = self.session.head(episode_url)
            # Some podcasts include transcript info in headers or metadata
            return response.status_code == 200
        except:
            return False
    
    def download_transcript(self, episode_data, output_dir):
        """Download transcript for a single episode"""
        episode_title = episode_data.get('title', 'Unknown Episode')
        safe_title = re.sub(r'[^\w\s-]', '', episode_title)
        safe_title = re.sub(r'[-\s]+', '-', safe_title)
        
        # Note: This is a template - actual transcript URLs vary by platform
        # Some platforms provide transcripts via:
        # - Dedicated transcript APIs
        # - Embedded JSON-LD data
        # - Third-party services like Otter.ai, Rev.com
        
        transcript_content = self.fetch_transcript_content(episode_data)
        
        if transcript_content:
            filename = f"{safe_title}.txt"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Episode: {episode_title}\n")
                f.write(f"Date: {episode_data.get('published', 'Unknown')}\n")
                f.write(f"URL: {episode_data.get('link', 'Unknown')}\n")
                f.write("-" * 50 + "\n\n")
                f.write(transcript_content)
            
            print(f"Downloaded: {filename}")
            return True
        else:
            print(f"No transcript available for: {episode_title}")
            return False
    
    def fetch_transcript_content(self, episode_data):
        """Fetch actual transcript content - implementation varies by platform"""
        # This is where you'd implement platform-specific transcript fetching
        # Examples of transcript sources:
        
        # 1. Direct transcript URLs (some podcasts provide these)
        # 2. Embedded JSON-LD data in episode pages
        # 3. Third-party transcript services
        # 4. Podcast-specific APIs
        
        # Placeholder implementation
        episode_url = episode_data.get('link', '')
        if not episode_url:
            return None
        
        try:
            # Try to find transcript in episode page
            response = self.session.get(episode_url)
            response.raise_for_status()
            
            # Look for common transcript patterns
            content = response.text
            
            # Check for JSON-LD transcript data
            json_ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', content, re.DOTALL)
            if json_ld_match:
                try:
                    ld_data = json.loads(json_ld_match.group(1))
                    if 'transcript' in ld_data:
                        return ld_data['transcript']
                except:
                    pass
            
            # Check for other transcript indicators
            # This would need to be customized per podcast platform
            
            return None
            
        except Exception as e:
            print(f"Error fetching transcript content: {e}")
            return None
    
    def download_all_transcripts(self, apple_podcast_url, output_dir="transcripts"):
        """Main method to download all available transcripts"""
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Extract podcast ID
        podcast_id = self.extract_podcast_id(apple_podcast_url)
        if not podcast_id:
            print("Could not extract podcast ID from URL")
            return
        
        # Get podcast info
        podcast_info = self.get_podcast_info(podcast_id)
        if not podcast_info:
            print("Could not fetch podcast information")
            return
        
        print(f"Podcast: {podcast_info.get('collectionName', 'Unknown')}")
        print(f"By: {podcast_info.get('artistName', 'Unknown')}")
        
        # Debug: Print all available keys
        print(f"Available podcast info keys: {list(podcast_info.keys())}")
        
        # Get RSS feed
        feed_url = podcast_info.get('feedUrl')
        if not feed_url:
            print("No RSS feed URL found in podcast info")
            print("This could mean:")
            print("1. The podcast doesn't provide an RSS feed")
            print("2. The podcast has been discontinued")
            print("3. The RSS feed is hosted elsewhere")
            return
        
        print(f"RSS Feed URL: {feed_url}")
        
        feed = self.get_rss_feed(feed_url)
        if not feed:
            return
        
        print(f"Found {len(feed.entries)} episodes")
        
        successful_downloads = 0
        failed_downloads = 0
        
        for i, entry in enumerate(feed.entries, 1):
            print(f"\nProcessing episode {i}/{len(feed.entries)}: {entry.title}")
            
            episode_data = {
                'title': entry.title,
                'link': entry.link,
                'published': entry.get('published', ''),
                'description': entry.get('summary', ''),
            }
            
            if self.download_transcript(episode_data, output_dir):
                successful_downloads += 1
            else:
                failed_downloads += 1
            
            # Be respectful with requests
            time.sleep(1)
        
        print(f"\nDownload complete!")
        print(f"Successful: {successful_downloads}")
        print(f"Failed: {failed_downloads}")

def main():
    """Example usage"""
    downloader = PodcastTranscriptDownloader()
    
    # Example URL - replace with actual Apple Podcasts URL
    podcast_url = input("Enter Apple Podcasts URL: ").strip()
    
    if not podcast_url:
        print("Please provide a valid Apple Podcasts URL")
        return
    
    output_directory = input("Enter output directory (default: transcripts): ").strip()
    if not output_directory:
        output_directory = "transcripts"
    
    downloader.download_all_transcripts(podcast_url, output_directory)

if __name__ == "__main__":
    # Required dependencies
    print("Required dependencies:")
    print("pip install requests feedparser")
    print("-" * 30)
    
    main()