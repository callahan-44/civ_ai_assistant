"""
Log file watcher for the Civ VI AI Advisor.
Monitors Lua.log for game state updates.
"""

import re
import json
import time
import threading
from pathlib import Path
from typing import Optional, Callable


class LogWatcher:
    """Watches the Civ VI Lua.log file for game state updates."""

    # Trim log when it exceeds 5MB
    MAX_LOG_SIZE = 5 * 1024 * 1024
    # Check for trim every N iterations (every ~30 seconds)
    TRIM_CHECK_INTERVAL = 30

    def __init__(self, log_path: str, callback: Callable[[dict], None]):
        self.log_path = Path(log_path)
        self.callback = callback
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_position = 0
        # Pattern for simple (non-chunked) format
        self.pattern_simple = re.compile(r">>>GAMESTATE>>>(.*?)<<<END<<<", re.DOTALL)
        # Pattern for chunked format: >>>GAMESTATE:N/M>>>...
        self.pattern_chunk = re.compile(r">>>GAMESTATE:(\d+)/(\d+)>>>(.*?)(?=>>>GAMESTATE:|<<<END<<<|$)", re.DOTALL)
        self.iteration_count = 0
        self.initialized = False

    def _extract_game_states(self, content: str) -> list:
        """
        Extract all complete game states from content.
        Handles both simple and chunked formats.
        Returns list of JSON strings.
        """
        game_states = []

        # First, find simple (non-chunked) game states
        for match in self.pattern_simple.finditer(content):
            game_states.append((match.start(), match.group(1).strip()))

        # Now find chunked game states
        # Each chunk looks like: >>>GAMESTATE:N/M>>>content
        # Chunks may span multiple log lines, and content continues until next chunk marker or <<<END<<<

        # Find all chunk markers with their positions
        chunk_marker_pattern = re.compile(r">>>GAMESTATE:(\d+)/(\d+)>>>")
        markers = [(m.start(), m.end(), int(m.group(1)), int(m.group(2))) for m in chunk_marker_pattern.finditer(content)]

        if not markers:
            game_states.sort(key=lambda x: x[0])
            return [gs[1] for gs in game_states]

        # Group markers into complete sets (1/N through N/N ending with <<<END<<<)
        i = 0
        while i < len(markers):
            start_pos, content_start, chunk_num, total_chunks = markers[i]

            # Check if this is chunk 1 of a set
            if chunk_num != 1:
                i += 1
                continue

            # Try to collect all chunks for this set
            chunks = {}
            set_complete = False
            j = i

            while j < len(markers):
                m_start, c_start, c_num, c_total = markers[j]

                # Check if this is a new set (chunk 1 appearing after we already started)
                if c_num == 1 and j > i:
                    break

                # Check if this marker belongs to the same set (same total)
                if c_total != total_chunks:
                    break

                # Find where this chunk's content ends
                if j + 1 < len(markers):
                    # Content ends at the next marker
                    next_marker_pos = markers[j + 1][0]
                    chunk_content = content[c_start:next_marker_pos]
                else:
                    # Last marker - content goes to end or <<<END<<<
                    chunk_content = content[c_start:]

                # Clean up: remove any trailing newlines and log prefixes
                # The content should stop at newline (unless it's the last chunk with <<<END<<<)
                if c_num < total_chunks:
                    # Not the last chunk - content ends at newline
                    newline_pos = chunk_content.find('\n')
                    if newline_pos >= 0:
                        chunk_content = chunk_content[:newline_pos]
                else:
                    # Last chunk - should end with <<<END<<<
                    end_marker_pos = chunk_content.find('<<<END<<<')
                    if end_marker_pos >= 0:
                        chunk_content = chunk_content[:end_marker_pos]
                        set_complete = True

                chunks[c_num] = chunk_content
                j += 1

                # If we've collected all chunks and the set is complete, stop
                if c_num == total_chunks:
                    break

            # If we have all chunks and the set is complete, reassemble
            if set_complete and len(chunks) == total_chunks:
                full_json = "".join(chunks[k] for k in range(1, total_chunks + 1))
                game_states.append((start_pos, full_json.strip()))

            # Move to the next potential set
            i = j if j > i else i + 1

        # Sort by position and return just the JSON strings
        game_states.sort(key=lambda x: x[0])
        return [gs[1] for gs in game_states]

    def start(self):
        """Start watching the log file."""
        self.running = True
        # On startup, find and send ONLY the most recent game state
        self._send_most_recent_state()
        self.thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.thread.start()

    def _send_most_recent_state(self):
        """Find and send only the most recent game state from the log."""
        try:
            if not self.log_path.exists():
                print("Log file not found, waiting for game...")
                return

            with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                # Move position to end of file for future reads
                self.last_position = f.tell()

            # Find ALL game states (handles both simple and chunked formats)
            game_state_jsons = self._extract_game_states(content)
            if game_state_jsons:
                # Only send the most recent (last) game state
                try:
                    game_state = json.loads(game_state_jsons[-1])
                    print(f"Found {len(game_state_jsons)} game state(s) in log, using most recent (turn {game_state.get('turn', '?')})")
                    self.callback(game_state)
                except json.JSONDecodeError as e:
                    print(f"JSON parse error on most recent state: {e}")
            else:
                print("No game states found in log yet")

            self.initialized = True

        except Exception as e:
            print(f"Error reading initial log state: {e}")

    def stop(self):
        """Stop watching the log file."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _trim_log_if_needed(self):
        """Trim the log file if it exceeds the maximum size."""
        try:
            if not self.log_path.exists():
                return

            file_size = self.log_path.stat().st_size
            if file_size > self.MAX_LOG_SIZE:
                print(f"Log file size ({file_size / 1024 / 1024:.1f}MB) exceeds limit, trimming...")

                # Read the last portion of the file to preserve recent entries
                keep_size = self.MAX_LOG_SIZE // 4  # Keep ~1.25MB of recent logs
                with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(max(0, file_size - keep_size))
                    # Skip partial line at the start
                    if file_size > keep_size:
                        f.readline()
                    recent_content = f.read()

                # Write back the trimmed content
                with open(self.log_path, "w", encoding="utf-8") as f:
                    f.write("--- Log trimmed by CivAI Advisor ---\n")
                    f.write(recent_content)

                # Reset read position to start of new file
                self.last_position = 0
                print("Log file trimmed successfully")

        except PermissionError:
            # Game might have the file locked, skip this trim attempt
            print("Could not trim log (file in use), will retry later")
        except Exception as e:
            print(f"Error trimming log: {e}")

    def _watch_loop(self):
        """Main loop that tails the log file."""
        # Buffer to accumulate content for chunk reassembly
        pending_content = ""

        while self.running:
            try:
                # Periodically check if log needs trimming
                self.iteration_count += 1
                if self.iteration_count >= self.TRIM_CHECK_INTERVAL:
                    self.iteration_count = 0
                    self._trim_log_if_needed()

                if self.log_path.exists():
                    # Check if file was truncated/rotated (position beyond file size)
                    file_size = self.log_path.stat().st_size
                    if self.last_position > file_size:
                        self.last_position = 0
                        pending_content = ""  # Reset buffer on file rotation

                    with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                        # Move to last known position
                        f.seek(self.last_position)
                        new_content = f.read()
                        self.last_position = f.tell()

                        # Add to pending buffer
                        pending_content += new_content

                        # Extract complete game states (handles chunked format)
                        game_state_jsons = self._extract_game_states(pending_content)
                        for gs_json in game_state_jsons:
                            try:
                                game_state = json.loads(gs_json)
                                self.callback(game_state)
                            except json.JSONDecodeError as e:
                                print(f"JSON parse error: {e}")

                        # Clear processed content from buffer (keep only after last <<<END<<<)
                        last_end = pending_content.rfind("<<<END<<<")
                        if last_end >= 0:
                            pending_content = pending_content[last_end + len("<<<END<<<"):]
                        # Prevent buffer from growing indefinitely
                        if len(pending_content) > 50000:
                            pending_content = pending_content[-10000:]

            except Exception as e:
                print(f"Log watcher error: {e}")

            time.sleep(1.0)  # Check every second
