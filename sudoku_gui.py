from __future__ import annotations

"""
Sudoku CSP Simulator (GUI).

Required UI features for the assignment:
- Algorithm selection (AC-3 or Backtracking)
- Difficulty selection (Easy / Medium / Hard) and Puzzle # (1-4)
- Time taken to solve (seconds)
- Hint assistance: reveal one correct value in an empty cell
"""

import os
import tkinter as tk
from tkinter import messagebox, ttk
import time
import threading

from sudoku_io import autofix_inconsistent_clues, read_board
from sudoku_solver import Algorithm, Grid, solve_board


class SudokuApp:
    def __init__(self) -> None:
        """Create the UI, load the default puzzle, and start the Tk event loop."""
        self.root = tk.Tk()
        self.root.title("Sudoku CSP Simulator")
        self.root.minsize(980, 680)

        self.algorithm_var = tk.StringVar(value="backtracking")
        self.difficulty_var = tk.StringVar(value="Easy")
        self.puzzle_var = tk.StringVar(value="1")
        self.stats_var = tk.StringVar(value="Ready.")

        self.original_board: Grid | None = None
        self.current_input: Grid | None = None
        self.current_solution: Grid | None = None  # AI/algorithm output shown on right
        self.validation_solution: Grid | None = None  # full solution used for gameplay validation
        self.fixed_cells: set[tuple[int, int]] = set()
        self.hint_cells: set[tuple[int, int]] = set()
        self.incorrect_cells: set[tuple[int, int]] = set()
        self.completed_boxes: set[tuple[int, int]] = set()
        self.box_flash_until: dict[tuple[int, int], float] = {}
        self.cell_pop_until: dict[tuple[int, int], float] = {}
        self.animation_job: str | None = None
        self.box_flash_duration_s: float = 0.6
        self.cell_pop_duration_s: float = 0.22

        self.selected_cell: tuple[int, int] | None = None
        self.selected_number: int | None = None
        self.score: int = 0
        self.strikes: int = 0
        self.game_over: bool = False
        self.solve_running: bool = False
        self.last_solve_time_s: float | None = None
        self.last_solve_algo: str = "-"
        self.last_calls: int = 0
        self.last_failures: int = 0
        self.game_start_ts: float | None = None
        self.timer_job: str | None = None
        self.loaded_board_key: tuple[str, str] | None = None

        # Retro/pixel-ish UI feel (Tk will fall back if unavailable).
        self.pixel_font_family: str = "Terminal"

        main = tk.Frame(self.root, padx=16, pady=16)
        main.pack(fill=tk.BOTH, expand=True)

        controls = tk.Frame(main)
        controls.pack(fill=tk.X)

        tk.Label(controls, text="Algorithm:", font=("Segoe UI", 10, "bold")).pack(
            side=tk.LEFT, padx=(0, 8)
        )

        algo_wrap = tk.Frame(controls)
        algo_wrap.pack(side=tk.LEFT, padx=(0, 12))
        tk.Radiobutton(
            algo_wrap,
            text="AC-3",
            value="ac3",
            variable=self.algorithm_var,
        ).pack(side=tk.LEFT)
        tk.Radiobutton(
            algo_wrap,
            text="Backtracking",
            value="backtracking",
            variable=self.algorithm_var,
        ).pack(side=tk.LEFT)

        tk.Label(controls, text="Difficulty:", font=("Segoe UI", 10, "bold")).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        difficulty_box = ttk.Combobox(
            controls,
            textvariable=self.difficulty_var,
            values=["Easy", "Medium", "Hard"],
            state="readonly",
            width=10,
        )
        difficulty_box.pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(controls, text="Puzzle #:", font=("Segoe UI", 10, "bold")).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        puzzle_box = ttk.Combobox(
            controls,
            textvariable=self.puzzle_var,
            values=["1", "2", "3", "4"],
            state="readonly",
            width=4,
        )
        puzzle_box.pack(side=tk.LEFT, padx=(0, 12))

        self.load_btn = tk.Button(controls, text="Load Board", command=self.load_selected_board)
        self.load_btn.pack(side=tk.LEFT, padx=4)
        self.solve_btn = tk.Button(controls, text="Solve", command=self.solve_selected_board)
        self.solve_btn.pack(side=tk.LEFT, padx=4)
        self.hint_btn = tk.Button(controls, text="Hint", command=self.give_hint)
        self.hint_btn.pack(side=tk.LEFT, padx=4)
        self.reset_btn = tk.Button(controls, text="Reset", command=self.reset_view)
        self.reset_btn.pack(side=tk.LEFT, padx=4)

        boards_wrap = tk.Frame(main)
        boards_wrap.pack(fill=tk.BOTH, expand=True, pady=(14, 0))

        self.input_panel = tk.Frame(boards_wrap)
        self.input_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.output_panel = tk.Frame(boards_wrap)
        self.output_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 0))

        tk.Label(
            self.input_panel,
            text="Input Board",
            font=("Segoe UI", 11, "bold"),
            anchor="center",
            justify="center",
        ).pack(fill=tk.X, pady=(0, 8), padx=(0, 120))
        tk.Label(
            self.output_panel, text="Game Panel", font=("Segoe UI", 11, "bold")
        ).pack(pady=(0, 8))

        self.input_canvas = tk.Canvas(
            self.input_panel, width=430, height=430, bg="#f3f3f3", highlightthickness=0
        )
        self.input_canvas.pack(fill=tk.BOTH, expand=True)
        self.input_canvas.bind("<Button-1>", self._on_input_click)
        self.input_canvas.configure(takefocus=1)

        # Logs (top half of right panel)
        log_wrap = tk.Frame(self.output_panel)
        log_wrap.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(
            log_wrap,
            height=12,
            wrap="word",
            font=("Consolas", 10),
            bg="#fbfbfb",
        )
        log_scroll = ttk.Scrollbar(log_wrap, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.insert("end", "Ready.\n")
        self.log_text.configure(state=tk.DISABLED)

        self.input_canvas.bind("<Configure>", lambda _e: self._draw_board(self.input_canvas, self.current_input))

        keypad = tk.Frame(self.input_panel)
        keypad.pack(fill=tk.X, pady=(10, 0))
        tk.Label(keypad, text="Numbers:", font=("Segoe UI", 10, "bold")).pack(
            anchor="center", pady=(0, 6)
        )
        pad = tk.Frame(keypad)
        pad.pack(anchor="center")
        self.keypad_buttons: list[tk.Button] = []
        for n in range(1, 10):
            btn = tk.Button(
                pad,
                text=str(n),
                width=3,
                font=(self.pixel_font_family, 12, "bold"),
                command=lambda v=n: self._on_number_press(v),
            )
            btn.grid(row=0, column=n - 1, padx=2, pady=2)
            self.keypad_buttons.append(btn)
        tk.Button(
            pad,
            text="Erase",
            width=6,
            font=(self.pixel_font_family, 11),
            command=self._on_erase_press,
        ).grid(row=0, column=9, padx=(10, 2), pady=2)

        self.root.bind("<Up>", lambda _e: self._move_selection(-1, 0))
        self.root.bind("<Down>", lambda _e: self._move_selection(1, 0))
        self.root.bind("<Left>", lambda _e: self._move_selection(0, -1))
        self.root.bind("<Right>", lambda _e: self._move_selection(0, 1))
        self.root.bind("<KeyPress>", self._on_key_press)

        # Bottom-right visible stats (under logs)
        right_stats = tk.Frame(self.output_panel)
        right_stats.pack(fill=tk.X, pady=(10, 0))
        self.score_var = tk.StringVar(value="Score: 0")
        self.strikes_var = tk.StringVar(value="Strikes: 0/3")
        self.ai_stats_var = tk.StringVar(value="AI: time=-  algo=-  calls=0  fails=0")
        self.timer_var = tk.StringVar(value="Time: 00:00.0")
        tk.Label(right_stats, textvariable=self.score_var, font=("Segoe UI", 11, "bold")).pack(
            anchor=tk.W
        )
        tk.Label(right_stats, textvariable=self.strikes_var, font=("Segoe UI", 11, "bold")).pack(
            anchor=tk.W
        )
        tk.Label(
            right_stats,
            textvariable=self.timer_var,
            font=("Segoe UI", 12, "bold"),
            justify="center",
        ).pack(anchor="center", pady=(8, 8))
        tk.Label(right_stats, textvariable=self.ai_stats_var, font=("Consolas", 10)).pack(
            anchor=tk.W, pady=(6, 0)
        )

        self.load_selected_board()
        self.root.mainloop()

    def _log(self, msg: str) -> None:
        """Append a line to the log panel."""
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert("end", msg.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state=tk.DISABLED)

    def _start_timer(self) -> None:
        """Start (or restart) the gameplay timer."""
        self._stop_timer()
        self.game_start_ts = time.perf_counter()
        self._tick_timer()

    def _stop_timer(self) -> None:
        """Stop the gameplay timer if running."""
        if self.timer_job is not None:
            try:
                self.root.after_cancel(self.timer_job)
            except Exception:
                pass
        self.timer_job = None

    def _tick_timer(self) -> None:
        """Update the timer label periodically."""
        if self.game_start_ts is None:
            self.timer_var.set("Time: 00:00.0")
        else:
            elapsed = time.perf_counter() - self.game_start_ts
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            tenths = int((elapsed * 10) % 10)
            self.timer_var.set(f"Time: {minutes:02d}:{seconds:02d}.{tenths}")

        if not self.game_over and not self.solve_running:
            self.timer_job = self.root.after(100, self._tick_timer)
        else:
            self.timer_job = None

    def _set_controls_enabled(self, enabled: bool) -> None:
        """Enable/disable top controls while a solve is running."""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.load_btn.config(state=state)
        self.solve_btn.config(state=state)
        self.hint_btn.config(state=state)
        self.reset_btn.config(state=state)

    def _set_game_action_buttons_enabled(self, enabled: bool) -> None:
        """Enable/disable only gameplay action buttons (Solve/Hint)."""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.solve_btn.config(state=state)
        self.hint_btn.config(state=state)

    def _current_board_key(self) -> tuple[str, str]:
        """Return a stable key for currently selected difficulty and puzzle."""
        return (self.difficulty_var.get().strip().lower(), self.puzzle_var.get().strip())

    def _selected_board_is_loaded(self) -> bool:
        """True if currently selected board matches loaded board in memory."""
        return self.loaded_board_key == self._current_board_key() and self.current_input is not None

    def _board_path(self) -> str:
        """Return the current selected board file path."""
        diff = self.difficulty_var.get().strip().lower()
        num = int(self.puzzle_var.get().strip())
        return os.path.join("sudoku_boards", f"{diff}_{num}.txt")

    def _canvas_geometry(self, canvas: tk.Canvas) -> tuple[float, float, float, float]:
        """Return (x0, y0, grid_size, cell_size) for a board canvas."""
        size = min(canvas.winfo_width(), canvas.winfo_height())
        if size <= 1:
            size = 430
        grid_size = float(int(size * 0.9))
        cell = grid_size / 9.0
        x0 = (size - grid_size) / 2.0
        y0 = (size - grid_size) / 2.0
        return x0, y0, grid_size, cell

    def _hit_test_cell(self, canvas: tk.Canvas, x: float, y: float) -> tuple[int, int] | None:
        """Map a canvas click position to a (row,col) cell, or None if outside grid."""
        x0, y0, grid_size, cell = self._canvas_geometry(canvas)
        if x < x0 or y < y0 or x >= x0 + grid_size or y >= y0 + grid_size:
            return None
        col = int((x - x0) // cell)
        row = int((y - y0) // cell)
        if 0 <= row < 9 and 0 <= col < 9:
            return (row, col)
        return None

    def _highlight_sets(self, board: Grid | None) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
        """
        Return (soft_highlight, hard_highlight) cell sets.
        - soft: same row/col as selected cell OR cells containing selected number
        - hard: selected cell itself
        """
        if board is None or self.selected_cell is None:
            return set(), set()
        sr, sc = self.selected_cell
        soft: set[tuple[int, int]] = set()
        hard: set[tuple[int, int]] = {(sr, sc)}

        for c in range(9):
            if c != sc:
                soft.add((sr, c))
        for r in range(9):
            if r != sr:
                soft.add((r, sc))

        n = self.selected_number
        if n is not None:
            for r in range(9):
                for c in range(9):
                    if board[r][c] == n and (r, c) != (sr, sc):
                        soft.add((r, c))
        return soft, hard

    def _prune_animation_state(self, now: float) -> None:
        """Drop expired animation timers."""
        self.box_flash_until = {k: t for k, t in self.box_flash_until.items() if t > now}
        self.cell_pop_until = {k: t for k, t in self.cell_pop_until.items() if t > now}

    def _schedule_animation_if_needed(self) -> None:
        """Continue redraw loop while any animation is active."""
        if self.animation_job is not None:
            return
        now = time.perf_counter()
        self._prune_animation_state(now)
        if self.box_flash_until or self.cell_pop_until:
            self.animation_job = self.root.after(33, self._animation_tick)

    def _animation_tick(self) -> None:
        """Single animation frame callback."""
        self.animation_job = None
        self._redraw_all()
        self._schedule_animation_if_needed()

    def _refresh_completed_boxes(self, *, flash_new: bool) -> None:
        """Recompute full 3x3 boxes and optionally flash newly completed ones."""
        if self.current_input is None:
            self.completed_boxes = set()
            self.box_flash_until = {}
            return

        full_now: set[tuple[int, int]] = set()
        for br in range(0, 9, 3):
            for bc in range(0, 9, 3):
                if all(
                    self.current_input[r][c] != 0
                    for r in range(br, br + 3)
                    for c in range(bc, bc + 3)
                ):
                    full_now.add((br, bc))

        if flash_new:
            now = time.perf_counter()
            for box in full_now - self.completed_boxes:
                self.box_flash_until[box] = now + self.box_flash_duration_s
                br, bc = box
                for r in range(br, br + 3):
                    for c in range(bc, bc + 3):
                        if self.current_input[r][c] != 0:
                            self.cell_pop_until[(r, c)] = now + self.cell_pop_duration_s
            self._schedule_animation_if_needed()

        self.completed_boxes = full_now

    def _register_cell_fill(self, r: int, c: int, old_val: int, new_val: int) -> None:
        """Track cell fill transitions for pop animation and box completion state."""
        if old_val == 0 and new_val != 0:
            self.cell_pop_until[(r, c)] = time.perf_counter() + self.cell_pop_duration_s
        self._refresh_completed_boxes(flash_new=True)
        self._schedule_animation_if_needed()

    def _draw_board(self, canvas: tk.Canvas, board: Grid | None) -> None:
        """Draw a Sudoku board onto a Tk canvas."""
        canvas.delete("all")

        x0, y0, grid_size, cell = self._canvas_geometry(canvas)
        now = time.perf_counter()
        if canvas == self.input_canvas:
            self._prune_animation_state(now)

        # Highlights (only on the input canvas)
        soft_highlight: set[tuple[int, int]] = set()
        hard_highlight: set[tuple[int, int]] = set()
        if canvas == self.input_canvas:
            # Completed 3x3 boxes get a soft tint; newly completed ones flash brighter.
            for (br, bc) in self.completed_boxes:
                flash_active = self.box_flash_until.get((br, bc), 0.0) > now
                fill = "#cfeecf" if flash_active else "#e8f6ea"
                canvas.create_rectangle(
                    x0 + bc * cell,
                    y0 + br * cell,
                    x0 + (bc + 3) * cell,
                    y0 + (br + 3) * cell,
                    fill=fill,
                    outline="",
                )
            soft_highlight, hard_highlight = self._highlight_sets(board)
            for (r, c) in soft_highlight:
                cx0 = x0 + c * cell
                cy0 = y0 + r * cell
                canvas.create_rectangle(
                    cx0,
                    cy0,
                    cx0 + cell,
                    cy0 + cell,
                    fill="#d9d9d9",
                    outline="",
                )
            for (r, c) in hard_highlight:
                cx0 = x0 + c * cell
                cy0 = y0 + r * cell
                canvas.create_rectangle(
                    cx0,
                    cy0,
                    cx0 + cell,
                    cy0 + cell,
                    fill="#c7c7c7",
                    outline="",
                )
            # Hint cells (green) should remain visible even when grey highlights apply.
            for (r, c) in self.hint_cells:
                cx0 = x0 + c * cell
                cy0 = y0 + r * cell
                canvas.create_rectangle(
                    cx0,
                    cy0,
                    cx0 + cell,
                    cy0 + cell,
                    fill="#b7f0c3",
                    outline="",
                )

        # Outer box
        canvas.create_rectangle(x0, y0, x0 + grid_size, y0 + grid_size, width=2)

        # Grid lines
        for i in range(1, 9):
            w = 2 if i % 3 == 0 else 1
            x = x0 + i * cell
            y = y0 + i * cell
            canvas.create_line(x, y0, x, y0 + grid_size, width=w)
            canvas.create_line(x0, y, x0 + grid_size, y, width=w)

        if board is None:
            return

        for r in range(9):
            for c in range(9):
                val = board[r][c]
                if val == 0:
                    continue
                x = x0 + (c + 0.5) * cell
                y = y0 + (r + 0.5) * cell
                is_fixed = (r, c) in self.fixed_cells if canvas == self.input_canvas else False
                is_incorrect = (r, c) in self.incorrect_cells if canvas == self.input_canvas else False
                size = max(14, int(cell * 0.45))
                if canvas == self.input_canvas:
                    until = self.cell_pop_until.get((r, c), 0.0)
                    if until > now:
                        # Brief pop-in effect for newly entered numbers.
                        factor = 1.0 + 0.28 * ((until - now) / self.cell_pop_duration_s)
                        size = max(14, int(size * factor))
                canvas.create_text(
                    x,
                    y,
                    text=str(val),
                    font=(self.pixel_font_family, size, "bold"),
                    fill="#111111" if is_fixed else ("#c62828" if is_incorrect else "#1d3f6e"),
                )

    def _redraw_all(self) -> None:
        """Redraw both input and output panels."""
        self._draw_board(self.input_canvas, self.current_input)
        self._schedule_animation_if_needed()
        # Right side is logs now.

    def _set_keypad_enabled(self, enabled: bool) -> None:
        """Enable or disable keypad buttons."""
        state = tk.NORMAL if enabled else tk.DISABLED
        for b in self.keypad_buttons:
            b.config(state=state)

    def reset_view(self) -> None:
        """Clear the current view (does not change the selected puzzle)."""
        self._stop_timer()
        if self.animation_job is not None:
            try:
                self.root.after_cancel(self.animation_job)
            except Exception:
                pass
        self.animation_job = None
        self.original_board = None
        self.current_input = None
        self.current_solution = None
        self.validation_solution = None
        self.fixed_cells = set()
        self.hint_cells = set()
        self.incorrect_cells = set()
        self.completed_boxes = set()
        self.box_flash_until = {}
        self.cell_pop_until = {}
        self.selected_cell = None
        self.selected_number = None
        self.score = 0
        self.strikes = 0
        self.game_over = False
        self.solve_running = False
        self.last_solve_time_s = None
        self.last_solve_algo = "-"
        self.last_calls = 0
        self.last_failures = 0
        self.loaded_board_key = None
        self._set_keypad_enabled(True)
        self._set_controls_enabled(True)
        self._set_game_action_buttons_enabled(True)
        self.stats_var.set("")
        self.score_var.set("Score: 0")
        self.strikes_var.set("Strikes: 0/3")
        self.ai_stats_var.set("AI: time=-  algo=-  calls=0  fails=0")
        self.timer_var.set("Time: 00:00.0")
        self._redraw_all()

    def load_selected_board(self) -> None:
        """Load the selected puzzle into the input panel."""
        self._stop_timer()
        path = self._board_path()
        try:
            board = read_board(path)
        except Exception as exc:
            messagebox.showerror("Load Error", str(exc))
            return

        fixed_board, cleared = autofix_inconsistent_clues(board)
        if cleared > 0:
            self._log(f"[Load] WARNING: board had conflicts; cleared {cleared} cells to 0.")

        self.original_board = [row[:] for row in fixed_board]
        self.current_input = [row[:] for row in fixed_board]
        self.loaded_board_key = self._current_board_key()
        self.fixed_cells = {(r, c) for r in range(9) for c in range(9) if fixed_board[r][c] != 0}
        self.selected_cell = None
        self.selected_number = None
        self.score = 0
        self.strikes = 0
        self.game_over = False
        self.hint_cells = set()
        self.incorrect_cells = set()
        self.completed_boxes = set()
        self.box_flash_until = {}
        self.cell_pop_until = {}
        self.current_solution = None  # right side should be empty until Solve is clicked
        self._set_keypad_enabled(True)
        self._set_controls_enabled(True)
        self._set_game_action_buttons_enabled(True)
        self._start_timer()

        # Pre-compute the full solution for validation / hints.
        solved, _stats = solve_board(fixed_board, algorithm="backtracking")
        self.validation_solution = solved

        if solved is None:
            self.stats_var.set(f"Loaded {path}\nNo solution available for gameplay/hints.")
            self._log(f"[Load] {path}: no solution (validation unavailable).")
        else:
            self.stats_var.set(
                f"Loaded {path}\nGame: Score={self.score}  Strikes={self.strikes}/3\n"
                f"Click a cell, then press a number (1-9)."
            )
            self._log(f"[Load] {path}: validation solution ready.")
        self._refresh_completed_boxes(flash_new=False)
        self._update_game_status()
        self._redraw_all()

    def solve_selected_board(self) -> None:
        """Solve the selected puzzle using the chosen algorithm and show stats."""
        if self.solve_running:
            return
        if self.game_over or self._check_game_complete():
            self.game_over = True
            self._set_game_action_buttons_enabled(False)
            self._update_game_status("Board already complete.")
            return
        if not self._selected_board_is_loaded():
            self._update_game_status("Selection changed. Click Load Board first.")
            messagebox.showinfo("Load Required", "Click 'Load Board' for the selected puzzle first.")
            return
        path = self._board_path()

        algo: Algorithm = "ac3" if self.algorithm_var.get() == "ac3" else "backtracking"
        algo_label = "AC-3" if algo == "ac3" else "Backtracking"
        self.solve_running = True
        self._stop_timer()
        self._set_controls_enabled(False)
        self._set_keypad_enabled(False)
        self._log(f"[Solve] Started... algo={algo_label} (from current player state)")

        start_state = [row[:] for row in self.current_input]

        def worker() -> None:
            t0 = time.perf_counter()
            solved, stats = solve_board(start_state, algorithm=algo)
            elapsed = time.perf_counter() - t0

            def apply_result() -> None:
                self.solve_running = False
                self.last_solve_time_s = elapsed
                self.last_solve_algo = algo_label
                self.last_calls = stats.backtrack_calls
                self.last_failures = stats.backtrack_failures

                self._log(
                    f"[Solve] Done | time={elapsed:.4f}s | calls={stats.backtrack_calls} fails={stats.backtrack_failures}"
                )

                if solved is None:
                    self._set_controls_enabled(True)
                    self._set_keypad_enabled(True)
                    self._update_game_status("AI could not solve from the current state.")
                else:
                    prev_board = [row[:] for row in self.current_input] if self.current_input is not None else None
                    self.current_input = solved
                    self.incorrect_cells = set()
                    if prev_board is not None:
                        for r in range(9):
                            for c in range(9):
                                if prev_board[r][c] == 0 and solved[r][c] != 0:
                                    self.cell_pop_until[(r, c)] = (
                                        time.perf_counter() + self.cell_pop_duration_s
                                    )
                    self._refresh_completed_boxes(flash_new=True)
                    self.game_over = True
                    self._stop_timer()
                    self._set_controls_enabled(True)
                    self._set_game_action_buttons_enabled(False)
                    self._set_keypad_enabled(False)
                    self._update_game_status("AI filled the remaining cells.")
                self._redraw_all()

            self.root.after(0, apply_result)

        threading.Thread(target=worker, daemon=True).start()

    def _update_game_status(self, extra_line: str | None = None) -> None:
        """Update the stats/status area for gameplay."""
        if self.current_input is None:
            return
        path = self._board_path()
        base = f"Loaded {path}\nGame: Score={self.score}  Strikes={self.strikes}/3"
        if extra_line:
            base += f"\n{extra_line}"
        self.stats_var.set(base)
        self.score_var.set(f"Score: {self.score}")
        self.strikes_var.set(f"Strikes: {self.strikes}/3")
        if self.last_solve_time_s is None:
            t = "-"
        else:
            t = f"{self.last_solve_time_s:.4f}s"
        self.ai_stats_var.set(
            f"AI: time={t}  algo={self.last_solve_algo}  calls={self.last_calls}  fails={self.last_failures}"
        )

    def _check_game_complete(self) -> bool:
        """Return True if all cells are filled (win check is against the solution)."""
        if self.current_input is None:
            return False
        return all(self.current_input[r][c] != 0 for r in range(9) for c in range(9))

    def _game_over(self, reason: str) -> None:
        """End the game and disable input."""
        self.game_over = True
        self._stop_timer()
        self._set_keypad_enabled(False)
        self._set_game_action_buttons_enabled(False)
        self._update_game_status(reason)
        messagebox.showinfo("Game Over", reason)

    def _award_points(self, correct: bool) -> None:
        """Simple scoring system (can be tweaked)."""
        if correct:
            self.score += 10
        else:
            self.score = max(0, self.score - 3)

    def _on_input_click(self, event: tk.Event) -> None:
        """Select a cell on the input board canvas."""
        if self.game_over:
            return
        if self.current_input is None:
            return
        self.input_canvas.focus_set()
        cell = self._hit_test_cell(self.input_canvas, float(event.x), float(event.y))
        if cell is None:
            return
        self.selected_cell = cell
        r, c = cell
        v = self.current_input[r][c]
        # Do not trigger number-highlighting when user clicks non-editable clue cells.
        if (r, c) in self.fixed_cells:
            self.selected_number = None
        else:
            self.selected_number = v if v != 0 else self.selected_number
        self._update_game_status(f"Selected cell ({r+1},{c+1}).")
        self._redraw_all()

    def _move_selection(self, dr: int, dc: int) -> None:
        """Move the current selection using arrow keys."""
        if self.root.focus_get() is not self.input_canvas:
            return
        if self.game_over or self.current_input is None:
            return
        if self.selected_cell is None:
            self.selected_cell = (0, 0)
            self._redraw_all()
            return
        r, c = self.selected_cell
        nr = max(0, min(8, r + dr))
        nc = max(0, min(8, c + dc))
        self.selected_cell = (nr, nc)
        v = self.current_input[nr][nc]
        self.selected_number = v if v != 0 else self.selected_number
        self._redraw_all()

    def _on_key_press(self, event: tk.Event) -> None:
        """Keyboard controls for board entry: 1-9 and Backspace/Delete erase."""
        if self.root.focus_get() is not self.input_canvas:
            return
        if self.game_over or self.current_input is None:
            return

        key = (event.keysym or "").lower()
        ch = event.char or ""

        if key in {"backspace", "delete"}:
            self._on_erase_press()
            return

        if ch in "123456789":
            self._on_number_press(int(ch))
            return

        if key.startswith("kp_") and len(key) == 4 and key[-1] in "123456789":
            self._on_number_press(int(key[-1]))
            return

    def _on_erase_press(self) -> None:
        """Erase a player-filled cell."""
        if self.game_over or self.current_input is None or self.selected_cell is None:
            return
        r, c = self.selected_cell
        if (r, c) in self.fixed_cells:
            self._update_game_status("Cannot erase a fixed clue cell.")
            return
        if (
            self.validation_solution is not None
            and self.current_input[r][c] != 0
            and self.current_input[r][c] == self.validation_solution[r][c]
        ):
            self._update_game_status(
                f"Cell ({r+1},{c+1}) is correct and locked. It cannot be erased."
            )
            return
        old_val = self.current_input[r][c]
        self.current_input[r][c] = 0
        self.incorrect_cells.discard((r, c))
        if old_val != 0:
            self._refresh_completed_boxes(flash_new=False)
        self._update_game_status(f"Erased cell ({r+1},{c+1}).")
        self._redraw_all()

    def _on_number_press(self, n: int) -> None:
        """
        Number-pad handler.
        - Always sets selected_number (so matching cells highlight)
        - If a cell is selected and editable, attempts to place the number
        """
        if self.game_over or self.current_input is None:
            return
        if self.selected_cell is None:
            self.selected_number = n
            self._update_game_status(f"Selected number {n}. Now click a cell.")
            self._redraw_all()
            return

        r, c = self.selected_cell
        if (r, c) in self.fixed_cells:
            self._update_game_status("That cell is a fixed clue.")
            self._redraw_all()
            return

        if self.validation_solution is None:
            self._update_game_status("No solution available for validation.")
            self._redraw_all()
            return

        correct_val = self.validation_solution[r][c]
        # Keep already-correct values stable unless user explicitly erases first.
        if self.current_input[r][c] != 0 and self.current_input[r][c] == correct_val:
            self._update_game_status(
                f"Cell ({r+1},{c+1}) is already correct. Erase first to change it."
            )
            self._redraw_all()
            return

        self.selected_number = n
        if n == correct_val:
            old_val = self.current_input[r][c]
            self.current_input[r][c] = n
            self.hint_cells.discard((r, c))
            self.incorrect_cells.discard((r, c))
            self._register_cell_fill(r, c, old_val, n)
            self._award_points(True)
            self._update_game_status(f"Correct: placed {n} at ({r+1},{c+1}). +10")
            self._redraw_all()
            if self._check_game_complete():
                self._game_over(f"You solved it! Final score={self.score}.")
            return

        old_val = self.current_input[r][c]
        self.current_input[r][c] = n
        self.incorrect_cells.add((r, c))
        self._register_cell_fill(r, c, old_val, n)
        self.strikes += 1
        self._award_points(False)
        self._update_game_status(
            f"Wrong: {n} at ({r+1},{c+1}) [shown in red]. Strike {self.strikes}/3"
        )
        self._redraw_all()
        if self.strikes >= 3:
            self._game_over(f"3 strikes. Game over. Final score={self.score}.")

    def give_hint(self) -> None:
        """Reveal one correct value in an empty cell (uses a computed solution)."""
        if self.game_over or self._check_game_complete():
            self.game_over = True
            self._set_game_action_buttons_enabled(False)
            self._update_game_status("Board already complete.")
            return
        if not self._selected_board_is_loaded():
            self._update_game_status("Selection changed. Click Load Board first.")
            messagebox.showinfo("Load Required", "Click 'Load Board' for the selected puzzle first.")
            return

        # Compute solution (using backtracking) if we don't have one yet.
        if self.validation_solution is None:
            solved, _stats = solve_board(self.current_input, algorithm="backtracking")
            if solved is None:
                messagebox.showinfo("Hint", "No solution available for this puzzle.")
                return
            self.validation_solution = solved

        def candidates_for_cell(rr: int, cc: int) -> set[int]:
            if self.current_input is None:
                return set()
            if self.current_input[rr][cc] != 0:
                return set()
            used = set()
            used.update(self.current_input[rr][k] for k in range(9) if self.current_input[rr][k] != 0)
            used.update(self.current_input[k][cc] for k in range(9) if self.current_input[k][cc] != 0)
            br = (rr // 3) * 3
            bc = (cc // 3) * 3
            for r2 in range(br, br + 3):
                for c2 in range(bc, bc + 3):
                    v = self.current_input[r2][c2]
                    if v != 0:
                        used.add(v)
            return set(range(1, 10)) - used

        # Smart hint: pick the empty cell with the fewest legal candidates (MRV).
        best_cell: tuple[int, int] | None = None
        best_count: int = 10
        for r in range(9):
            for c in range(9):
                if self.current_input[r][c] != 0:
                    continue
                cand = candidates_for_cell(r, c)
                if not cand:
                    continue
                if len(cand) < best_count:
                    best_count = len(cand)
                    best_cell = (r, c)
                    if best_count == 1:
                        break
            if best_count == 1:
                break

        if best_cell is None:
            messagebox.showinfo("Hint", "No valid hint cell found from the current state.")
            return

        r, c = best_cell
        old_val = self.current_input[r][c]
        self.current_input[r][c] = self.validation_solution[r][c]
        self.hint_cells.add((r, c))
        self.incorrect_cells.discard((r, c))
        self._register_cell_fill(r, c, old_val, self.current_input[r][c])
        self.score = max(0, self.score - 2)
        self._update_game_status(
            f"Hint: filled ({r+1},{c+1}) = {self.validation_solution[r][c]}  (-2 score)"
        )
        self._redraw_all()
        return

        messagebox.showinfo("Hint", "No empty cells left to hint.")


if __name__ == "__main__":
    SudokuApp()
