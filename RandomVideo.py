import os
import random
import sys
import pygame
import time
import threading
import queue
from moviepy.editor import VideoFileClip

class FrameLoader(threading.Thread):
    def __init__(self, video_path, start_time, end_time, frame_queue, actual_fps, preload_size=120):
        super().__init__()
        self.video_path = video_path
        self.start_time = start_time
        self.end_time = end_time
        self.frame_queue = frame_queue
        self.actual_fps = actual_fps
        self.preload_size = preload_size
        self.daemon = True
        self.stop_event = threading.Event()
        self.error = None
        self.clip = None

    def run(self):
        try:
            self.clip = VideoFileClip(self.video_path)
            subclip = (self.clip.subclip(self.start_time, self.end_time)
                      .set_fps(self.actual_fps))
            
            for frame in subclip.iter_frames(fps=self.actual_fps, dtype="uint8"):
                if self.stop_event.is_set():
                    break
                    
                try:
                    self.frame_queue.put(frame, timeout=1)
                except queue.Full:
                    if self.stop_event.is_set():
                        break
                    continue
                    
                while (self.frame_queue.qsize() >= self.preload_size and 
                       not self.stop_event.is_set()):
                    time.sleep(0.01)
                    
        except Exception as e:
            self.error = e
            print(f"FrameLoader error: {e}")
        finally:
            if self.clip is not None:
                self.clip.close()
            try:
                self.frame_queue.put(None, timeout=1)
            except queue.Full:
                pass

    def stop(self):
        self.stop_event.set()
        if self.clip is not None:
            self.clip.close()

class MoviePlayer:
    def __init__(self, movies_dir, min_interval, max_interval, target_fps=24, max_videos=None):
        print(f"Initializing MoviePlayer\n"
              f"Movies directory: {movies_dir}\n"
              f"Min interval: {min_interval} seconds\n"
              f"Max interval: {max_interval} seconds\n"
              f"Target FPS: {target_fps} FPS\n"
              f"Max videos: {max_videos if max_videos else 'unlimited'}")
        self.movies_dir = movies_dir
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.target_fps = target_fps
        self.max_videos = max_videos
        self.movie_files, self.movie_durations, self.movie_fps, self.movie_sizes = self.get_movie_files()
        print(f"Found {len(self.movie_files)} suitable video files\n")
        
        if not self.movie_files:
            raise ValueError("No suitable video files found in the specified directory")
            
        self.playlist = list(self.movie_files)
        random.shuffle(self.playlist)
        self.current_index = 0

    def get_movie_files(self):
        movie_files = [
            os.path.join(self.movies_dir, f) for f in os.listdir(self.movies_dir)
            if f.lower().endswith((".mov", ".mp4", ".avi", ".mkv"))
        ]
        movie_durations = {}
        movie_fps = {}
        movie_sizes = {}
        suitable_movies = []
        
        print(f"Loading {len(movie_files)} video files...")
        
        random.shuffle(movie_files)
        
        for index, file in enumerate(movie_files, start=1):
            if self.max_videos and len(suitable_movies) >= self.max_videos:
                break
            try:
                with VideoFileClip(file) as clip:
                    duration = int(clip.duration)
                    fps = clip.fps
                    size = clip.size
                    if duration >= self.min_interval:
                        movie_durations[file] = duration
                        movie_fps[file] = fps
                        movie_sizes[file] = size
                        suitable_movies.append(file)
                    print(f"Loaded {index}/{len(movie_files)}: {os.path.basename(file)} "
                          f"(Duration: {duration}s, FPS: {fps}, Size: {size[0]}x{size[1]})")
            except Exception as e:
                print(f"Error loading {file}: {e}")
        
        return suitable_movies, movie_durations, movie_fps, movie_sizes

    def calculate_window_size(self):
        """Calculate initial window size based on screen resolution"""
        screen_info = pygame.display.Info()
        screen_w = screen_info.current_w
        screen_h = screen_info.current_h
        
        # Use 90% of the screen size for the window
        window_w = int(screen_w * 0.9)
        window_h = int(screen_h * 0.9)
        
        return (window_w, window_h)

    def calculate_display_size(self, video_size, window_size):
        """Calculate the size to display the video maintaining aspect ratio and fitting window"""
        video_w, video_h = video_size
        window_w, window_h = window_size
        
        # Calculate both width and height scaling factors
        width_scale = window_w / video_w
        height_scale = window_h / video_h
        
        # Use the smaller scaling factor to ensure video fits window
        scale = min(width_scale, height_scale)
        
        # Calculate new dimensions
        new_width = int(video_w * scale)
        new_height = int(video_h * scale)
        
        return (new_width, new_height)

    def calculate_centered_position(self, video_size, window_size):
        """Calculate position to center the video in window"""
        video_w, video_h = video_size
        window_w, window_h = window_size
        
        x = (window_w - video_w) // 2
        y = (window_h - video_h) // 2
        
        return (x, y)

    def play_playlist(self):
        pygame.init()
        pygame.font.init()
        font = pygame.font.SysFont(None, 30)
        clock = pygame.time.Clock()

        # Set initial window size based on screen resolution
        window_size = self.calculate_window_size()
        screen = pygame.display.set_mode(window_size, pygame.RESIZABLE)
        pygame.display.set_caption("Movie Player - Press 'S' to skip, 'Q' to quit")
        
        try:
            while True:
                if self.current_index >= len(self.playlist):
                    random.shuffle(self.playlist)
                    self.current_index = 0
                    print("All videos played. Reshuffling playlist.")
                
                movie_file = self.playlist[self.current_index]
                self.current_index += 1

                try:
                    self._play_single_video(movie_file, font, clock, screen)
                except Exception as e:
                    print(f"Error playing {movie_file}: {e}")
                    continue
                
        except KeyboardInterrupt:
            print("\nStopping playback...")
        finally:
            pygame.quit()

    def _play_single_video(self, movie_file, font, clock, screen):
        duration = self.movie_durations[movie_file]
        original_fps = self.movie_fps[movie_file]
        playback_fps = self.target_fps
        video_size = self.movie_sizes[movie_file]
        
        play_duration = random.randint(
            self.min_interval, 
            min(self.max_interval, duration)
        ) if duration >= self.min_interval else duration
        
        start_time = random.randint(0, duration - play_duration) if duration > play_duration else 0
        end_time = start_time + play_duration
        
        frame_queue = queue.Queue(maxsize=240)
        loader = FrameLoader(movie_file, start_time, end_time, frame_queue, playback_fps)
        loader.start()

        try:
            self._play_frames(
                screen, frame_queue, playback_fps, play_duration,
                movie_file, font, loader, video_size
            )
        finally:
            loader.stop()
            loader.join(timeout=1)

    def _play_frames(self, screen, frame_queue, fps, duration, movie_file, font, loader, video_size):
        frame_time = 1.0 / fps
        next_frame_time = time.time()
        elapsed_time = 0
        
        file_size_mb = os.path.getsize(movie_file) / (1024 * 1024)
        filename = os.path.basename(movie_file)
        
        while True:
            current_time = time.time()
            
            if current_time < next_frame_time:
                time.sleep(max(0, next_frame_time - current_time))
                continue

            try:
                frame = frame_queue.get(timeout=1)
                if frame is None:  # End of video
                    break
            except queue.Empty:
                if loader.error:
                    raise loader.error
                print("Frame queue empty, skipping video.")
                break

            if self._handle_events(screen):
                break

            # Convert and display frame
            try:
                frame_surface = pygame.image.frombuffer(
                    frame.tobytes(), frame.shape[1::-1], "RGB"
                )
                
                # Calculate display size and position
                window_size = screen.get_size()
                display_size = self.calculate_display_size(video_size, window_size)
                display_pos = self.calculate_centered_position(display_size, window_size)
                
                # Scale frame and position it
                if display_size != video_size:
                    frame_surface = pygame.transform.smoothscale(frame_surface, display_size)
                
                # Fill screen with black
                screen.fill((0, 0, 0))
                
                # Blit frame at centered position
                screen.blit(frame_surface, display_pos)
                
                # Update display information
                self._update_display_info(
                    screen, font, elapsed_time, duration, fps, file_size_mb, filename
                )
                
                pygame.display.flip()
                
            except Exception as e:
                print(f"Error displaying frame: {e}")
                continue

            elapsed_time += frame_time
            next_frame_time = current_time + frame_time

    def _handle_events(self, screen):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_s:
                    return True
                elif event.key == pygame.K_q:
                    pygame.quit()
                    sys.exit()
            elif event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
        return False

    def _update_display_info(self, screen, font, elapsed_time, duration, fps, file_size_mb, filename):
        current = f"{int(elapsed_time // 60):02d}:{int(elapsed_time % 60):02d}"
        total = f"{int(duration // 60):02d}:{int(duration % 60):02d}"
        
        info_texts = [
            (filename, (10, 10)),  # Add filename at the top
            (f"Time: {current} / {total}", (10, 40)),
            (f"FPS: {fps}", (10, 70)),
            (f"Size: {file_size_mb:.2f} MB", (10, 100))
        ]
        
        # Create semi-transparent background for text
        for text, pos in info_texts:
            text_surface = font.render(text, True, (255, 255, 255))
            text_rect = text_surface.get_rect(topleft=pos)
            # Draw black background with alpha
            s = pygame.Surface((text_rect.width, text_rect.height))
            s.fill((0, 0, 0))
            s.set_alpha(128)
            screen.blit(s, text_rect)
            # Draw text
            screen.blit(text_surface, pos)

def main():
    movies_dir = sys.argv[1] if len(sys.argv) >= 2 else "."
    min_interval = int(sys.argv[2]) if len(sys.argv) >= 3 else 30
    max_interval = int(sys.argv[3]) if len(sys.argv) >= 4 else 60
    max_videos = int(sys.argv[4]) if len(sys.argv) >= 5 else None
    target_fps = int(sys.argv[5]) if len(sys.argv) >= 6 else 24

    if max_interval < min_interval:
        print("Error: max_interval must be greater than or equal to min_interval")
        sys.exit(1)
    
    if max_videos is not None and max_videos <= 0:
        print("Error: max_videos must be a positive integer")
        sys.exit(1)

    try:
        player = MoviePlayer(movies_dir, min_interval, max_interval, target_fps, max_videos)
        player.play_playlist()
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
