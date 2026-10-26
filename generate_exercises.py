#!/usr/bin/env python3
"""
generate_exercises.py — Strategic Understanding
Pure-Python PGN reader + FEN extractor. No external dependencies.

Usage:
  python3 generate_exercises.py <pgn_file> <session_slug>
  e.g.: python3 generate_exercises.py ttc_101326.pgn TTC_101326
"""

import sys, os, re

# ── PGN parser (minimal, no deps) ────────────────────────────────────────────
def parse_pgn(path):
    """Yield (headers, moves_san) for each game."""
    with open(path, encoding='utf-8', errors='replace') as f:
        text = f.read()

    game_blocks = re.split(r'\n(?=\[Event )', text)
    for block in game_blocks:
        block = block.strip()
        if not block:
            continue
        headers = {}
        for m in re.finditer(r'\[(\w+)\s+"([^"]*)"\]', block):
            headers[m.group(1)] = m.group(2)
        # Strip headers + comments
        movetext = re.sub(r'\[[^\]]*\]', '', block)
        movetext = re.sub(r'\{[^}]*\}', '', movetext)
        movetext = re.sub(r'\([^)]*\)', '', movetext)
        movetext = re.sub(r'\d+\.+', ' ', movetext)
        movetext = re.sub(r'[01](-[01])|1/2-1/2|\*', '', movetext)
        moves = movetext.split()
        moves = [m for m in moves if re.match(r'^[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](=[QRBN])?[+#]?$|^O-O(-O)?[+#]?$', m)]
        if headers and moves:
            yield headers, moves

# ── Minimal board / FEN generator (pure Python) ──────────────────────────────
INIT_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

FILES = 'abcdefgh'

def fen_to_board(fen):
    """Return 8x8 list (rank8..rank1) of piece chars or '.'"""
    rows = fen.split()[0].split('/')
    board = []
    for row in rows:
        rank = []
        for ch in row:
            if ch.isdigit():
                rank.extend(['.'] * int(ch))
            else:
                rank.append(ch)
        board.append(rank)
    return board  # board[0] = rank 8

def board_to_fen_part(board):
    rows = []
    for rank in board:
        s = ''
        empty = 0
        for sq in rank:
            if sq == '.':
                empty += 1
            else:
                if empty:
                    s += str(empty); empty = 0
                s += sq
        if empty:
            s += str(empty)
        rows.append(s)
    return '/'.join(rows)

def sq_to_rc(sq):
    """'e4' -> (row, col) where row 0=rank8"""
    f = FILES.index(sq[0])
    r = 8 - int(sq[1])
    return r, f

def rc_to_sq(r, c):
    return FILES[c] + str(8 - r)

class Board:
    def __init__(self, fen=INIT_FEN):
        parts = fen.split()
        self.grid = fen_to_board(fen)
        self.side = parts[1]  # 'w' or 'b'
        self.castle = parts[2]
        self.ep = parts[3]
        self.half = int(parts[4])
        self.full = int(parts[5])

    def fen(self):
        return f"{board_to_fen_part(self.grid)} {self.side} {self.castle} {self.ep} {self.half} {self.full}"

    def piece_at(self, r, c):
        if 0 <= r < 8 and 0 <= c < 8:
            return self.grid[r][c]
        return None

    def find_piece(self, piece_char):
        """Find all (r,c) of a piece."""
        result = []
        for r in range(8):
            for c in range(8):
                if self.grid[r][c] == piece_char:
                    result.append((r, c))
        return result

    def apply_san(self, san):
        """Apply a SAN move. Minimal — handles most common cases."""
        san = re.sub(r'[+#!?]', '', san)
        side = self.side
        upper = side == 'w'

        # Castling
        if san == 'O-O':
            r = 7 if upper else 0
            self.grid[r][4] = '.'
            self.grid[r][6] = 'K' if upper else 'k'
            self.grid[r][7] = '.'
            self.grid[r][5] = 'R' if upper else 'r'
            if upper: self.castle = self.castle.replace('K','').replace('Q','')
            else:     self.castle = self.castle.replace('k','').replace('q','')
            self._flip()
            return
        if san == 'O-O-O':
            r = 7 if upper else 0
            self.grid[r][4] = '.'
            self.grid[r][2] = 'K' if upper else 'k'
            self.grid[r][0] = '.'
            self.grid[r][3] = 'R' if upper else 'r'
            if upper: self.castle = self.castle.replace('K','').replace('Q','')
            else:     self.castle = self.castle.replace('k','').replace('q','')
            self._flip()
            return

        # Promotion
        promo = None
        m = re.match(r'(.+)=([QRBN])$', san)
        if m:
            san = m.group(1)
            promo = m.group(2) if upper else m.group(2).lower()

        # Parse destination
        dest_sq = san[-2:]
        dr, dc = sq_to_rc(dest_sq)

        # Piece type
        if san[0].isupper() and san[0] != san[0].lower():
            piece_type = san[0]
            disambiguation = san[1:-2]
        else:
            piece_type = 'P'
            disambiguation = san[:-2].replace('x','')

        piece_char = piece_type if upper else piece_type.lower()

        # Find source
        candidates = self.find_piece(piece_char)
        src = self._resolve(piece_type, candidates, dr, dc, disambiguation)

        if src is None:
            return  # couldn't resolve — skip

        sr, sc = src
        # Move
        self.grid[dr][dc] = promo if promo else piece_char
        self.grid[sr][sc] = '.'

        # En passant capture
        if piece_type == 'P' and dest_sq == self.ep and self.ep != '-':
            ep_r = dr + (1 if upper else -1)
            self.grid[ep_r][dc] = '.'

        # Update EP
        if piece_type == 'P' and abs(dr - sr) == 2:
            ep_r = (dr + sr) // 2
            self.ep = FILES[dc] + str(8 - ep_r)
        else:
            self.ep = '-'

        # Update castling rights if king/rook moved
        if piece_type == 'K':
            if upper: self.castle = self.castle.replace('K','').replace('Q','')
            else:     self.castle = self.castle.replace('k','').replace('q','')
        if piece_type == 'R':
            if upper:
                if sc == 7 and sr == 7: self.castle = self.castle.replace('K','')
                if sc == 0 and sr == 7: self.castle = self.castle.replace('Q','')
            else:
                if sc == 7 and sr == 0: self.castle = self.castle.replace('k','')
                if sc == 0 and sr == 0: self.castle = self.castle.replace('q','')

        if not self.castle: self.castle = '-'
        self._flip()

    def _flip(self):
        self.side = 'b' if self.side == 'w' else 'w'
        if self.side == 'w':
            self.full += 1

    def _resolve(self, piece_type, candidates, dr, dc, disambiguation):
        """Pick the right source square from candidates."""
        # Filter by disambiguation
        filtered = []
        for r, c in candidates:
            if disambiguation:
                if disambiguation[0] in FILES:
                    if c != FILES.index(disambiguation[0]):
                        continue
                elif disambiguation[0].isdigit():
                    if r != 8 - int(disambiguation[0]):
                        continue
            if self._can_move(piece_type, r, c, dr, dc):
                filtered.append((r, c))
        if len(filtered) == 1:
            return filtered[0]
        if filtered:
            return filtered[0]
        return candidates[0] if candidates else None

    def _can_move(self, piece_type, sr, sc, dr, dc):
        """Basic legality check (no check detection)."""
        if piece_type == 'P':
            upper = self.side == 'w'
            direction = -1 if upper else 1
            if sc == dc:  # forward
                if dr == sr + direction: return True
                if dr == sr + 2 * direction and (sr == 6 if upper else sr == 1):
                    return True
            else:  # capture
                if abs(dc - sc) == 1 and dr == sr + direction:
                    return True
        elif piece_type == 'N':
            return (abs(dr-sr), abs(dc-sc)) in [(2,1),(1,2)]
        elif piece_type == 'B':
            return abs(dr-sr) == abs(dc-sc)
        elif piece_type == 'R':
            return dr == sr or dc == sc
        elif piece_type == 'Q':
            return dr == sr or dc == sc or abs(dr-sr) == abs(dc-sc)
        elif piece_type == 'K':
            return max(abs(dr-sr), abs(dc-sc)) == 1
        return True

    def copy(self):
        import copy
        return copy.deepcopy(self)

def replay_to_move(moves, target_half):
    """Replay moves up to target half-move, return FEN."""
    board = Board()
    for i, san in enumerate(moves):
        if i >= target_half:
            break
        try:
            board.apply_san(san)
        except Exception:
            pass
    return board.fen()

# ── Config ──────────────────────────────────────────────────────────────────
PHASES = [
    ("transition_mg", "Transition to Middlegame", 10, "tmg"),
    ("middlegame",    "Middlegame",                10, "mid"),
    ("transition_eg", "Transition to Endgame",    10, "teg"),
    ("endgame",       "Basic Endgame",             10, "end"),
]

PHASE_HALF_MOVE = {
    "transition_mg": 24,   # ~move 12
    "middlegame":    40,   # ~move 20
    "transition_eg": 58,   # ~move 29
    "endgame":       72,   # ~move 36
}

# ── HTML template ────────────────────────────────────────────────────────────
EXERCISE_HTML = '''\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Strategic Understanding</title>
<style>
:root{{--fs:17px;--paper:#fbfaf7;--ink:#1d1f22;--muted:#5d6670;--line:#e2e0da;--card:#fff;--main:#1f4fa3;--mainbg:#1f4fa3;--mainfg:#fff;--btn:#fff;--btnb:#cfd5db;--gold:#b07d10;--correct:#166534;--correct-bg:#f0fdf4;--wrong:#9b1c1c;--wrong-bg:#fef2f2}}
:root[data-theme="dark"]{{--paper:#16191d;--ink:#e4e6e9;--muted:#9aa3ad;--line:#2c3238;--card:#1d2126;--main:#86b4ff;--mainbg:#2f5ea8;--mainfg:#fff;--btn:#232930;--btnb:#3a434c;--gold:#c9a030;--correct:#4ade80;--correct-bg:#0f2a1a;--wrong:#fca5a5;--wrong-bg:#3a0000;color-scheme:dark}}
@media(prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--paper:#16191d;--ink:#e4e6e9;--muted:#9aa3ad;--line:#2c3238;--card:#1d2126;--main:#86b4ff;--mainbg:#2f5ea8;--mainfg:#fff;--btn:#232930;--btnb:#3a434c;--gold:#c9a030;--correct:#4ade80;--correct-bg:#0f2a1a;--wrong:#fca5a5;--wrong-bg:#3a0000;color-scheme:dark}}}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:var(--paper);color:var(--ink)}}
body{{font-family:system-ui,'Segoe UI',sans-serif;font-size:var(--fs);line-height:1.6}}
.topbar{{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:10px;padding:8px 20px;background:var(--paper);border-bottom:1px solid var(--line);font-size:14px;flex-wrap:wrap}}
.back{{color:var(--main);text-decoration:none;font-weight:600;font-size:13px}}
.back:hover{{text-decoration:underline}}
.sp{{flex:1}}
.dk-btn{{font:inherit;font-size:13px;background:var(--btn);color:var(--ink);border:1px solid var(--btnb);border-radius:6px;padding:4px 10px;cursor:pointer}}
.page{{max-width:980px;margin:0 auto;padding:28px 16px 80px}}
.kicker{{font-size:.68rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--gold);margin-bottom:6px}}
h1{{font-size:1.15rem;font-weight:700;margin-bottom:18px;line-height:1.3}}
.layout{{display:grid;grid-template-columns:auto 1fr;gap:36px;align-items:start}}
@media(max-width:720px){{.layout{{grid-template-columns:1fr}}}}
.board-col{{}}
.board-wrap{{position:relative;display:inline-block}}
canvas{{display:block;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,.15)}}
.coord-files{{display:flex;justify-content:space-around;padding:2px 0 0;font-size:.65rem;color:var(--muted);font-weight:600;letter-spacing:.04em;font-family:system-ui}}
.coord-ranks{{position:absolute;left:-18px;top:0;bottom:0;display:flex;flex-direction:column;justify-content:space-around;font-size:.65rem;color:var(--muted);font-weight:600;font-family:system-ui}}
.game-link{{margin-top:10px;font-size:.8rem;text-align:center}}
.game-link a{{color:var(--main);text-decoration:none;font-weight:600}}
.game-link a:hover{{text-decoration:underline}}
.to-move{{margin-top:6px;font-size:.8rem;color:var(--muted);text-align:center;font-family:system-ui}}
.text-col{{}}
.question{{font-size:1rem;font-weight:600;margin-bottom:16px;line-height:1.45}}
.choice{{border:2px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:10px;cursor:pointer;transition:border-color .15s,background .15s}}
.choice:hover{{border-color:var(--main);background:color-mix(in srgb,var(--main) 4%,var(--card))}}
.choice.correct{{border-color:var(--correct);background:var(--correct-bg)}}
.choice.wrong{{border-color:var(--wrong);background:var(--wrong-bg)}}
.choice-head{{display:flex;align-items:baseline;gap:10px;margin-bottom:4px}}
.choice-letter{{font-weight:800;font-size:1rem;color:var(--main);min-width:18px}}
.choice-plan{{font-weight:700;font-size:.92rem}}
.choice-body{{font-size:.85rem;color:var(--muted);line-height:1.4;padding-left:28px}}
.verdict{{display:none;margin:12px 0;padding:10px 14px;border-radius:8px;font-size:.9rem;font-weight:600}}
.verdict.ok{{background:var(--correct-bg);color:var(--correct);border:1px solid var(--correct)}}
.verdict.no{{background:var(--wrong-bg);color:var(--wrong);border:1px solid var(--wrong)}}
.more-btn{{display:none;margin-top:8px;font:inherit;font-size:.85rem;background:none;border:none;color:var(--main);cursor:pointer;padding:4px 0;font-weight:600}}
.explanation{{display:none;margin-top:16px;padding:14px 16px;background:var(--card);border:1px solid var(--line);border-radius:8px;font-size:.88rem;line-height:1.6}}
.explanation h3{{font-size:.95rem;font-weight:700;margin-bottom:8px}}
.explanation p{{margin-bottom:8px;color:var(--muted)}}
.explanation p:last-child{{margin-bottom:0}}
.nav-row{{display:flex;gap:10px;margin-top:32px;flex-wrap:wrap}}
.nav-btn{{padding:8px 18px;border-radius:8px;border:1px solid var(--btnb);color:var(--ink);text-decoration:none;background:var(--btn);font-size:.88rem;font-family:system-ui}}
.nav-btn.main{{background:var(--mainbg);color:var(--mainfg);border-color:var(--mainbg);font-weight:600}}
.players{{font-size:.8rem;color:var(--muted);margin-bottom:14px;font-family:system-ui}}
</style>
</head>
<body>

<div class="topbar">
  <a class="back" href="../../../index.html">&#127968; Home</a>
  <span style="color:var(--muted);font-size:12px">&#8250;</span>
  <a class="back" href="../../../training.html">Training</a>
  <span style="color:var(--muted);font-size:12px">&#8250;</span>
  <a class="back" href="../index.html">{session}</a>
  <span style="color:var(--muted);font-size:12px">&#8250;</span>
  <span style="color:var(--muted);font-size:13px">{phase_label} {ex_num}</span>
  <span class="sp"></span>
  <button class="dk-btn" id="dk">Dark</button>
</div>

<div class="page">
  <div class="kicker">{phase_label} &middot; Exercise {ex_num}</div>
  <h1>{title}</h1>
  <div class="players">{players}</div>

  <div class="layout">
    <div class="board-col">
      <div class="board-wrap">
        <div class="coord-ranks" id="coord-ranks"></div>
        <canvas id="board" width="400" height="400"></canvas>
        <div class="coord-files" id="coord-files"></div>
      </div>
      <div class="game-link">
        <a href="{game_url}" target="_blank" rel="noopener">View full game on Chess.com &#8599;</a>
      </div>
      <div class="to-move" id="to-move"></div>
    </div>

    <div class="text-col">
      <p class="question">{question}</p>

      <div class="choice" id="cA" onclick="pick(\'A\')">
        <div class="choice-head">
          <span class="choice-letter">A</span>
          <span class="choice-plan">{plan_a_title}</span>
        </div>
        <div class="choice-body">{plan_a_body}</div>
      </div>

      <div class="choice" id="cB" onclick="pick(\'B\')">
        <div class="choice-head">
          <span class="choice-letter">B</span>
          <span class="choice-plan">{plan_b_title}</span>
        </div>
        <div class="choice-body">{plan_b_body}</div>
      </div>

      <div class="choice" id="cC" onclick="pick(\'C\')">
        <div class="choice-head">
          <span class="choice-letter">C</span>
          <span class="choice-plan">{plan_c_title}</span>
        </div>
        <div class="choice-body">{plan_c_body}</div>
      </div>

      <div class="verdict ok" id="v-ok">&#10003; Correct &mdash; {correct} is the best plan.</div>
      <div class="verdict no" id="v-no">&#10007; Not quite. The answer is Plan {correct}.</div>

      <button class="more-btn" id="more-btn" onclick="showExplanation()">Full explanation &#8595;</button>

      <div class="explanation" id="explanation">
        <h3>Why Plan {correct}?</h3>
        {explanation}
      </div>

      <div class="nav-row">
        {prev_link}
        <a class="nav-btn" href="../index.html">&#8593; Session</a>
        {next_link}
      </div>
    </div>
  </div>
</div>

<script>
const FEN = \'{fen}\';
const HL  = {hl};
const CORRECT = \'{correct}\';
const DONE_KEY = \'su-ttc101326\';
const EX_KEY   = \'{phase_id}-{ex_num_int}\';

function parseFen(fen) {{
  const ranks = fen.split(\' \')[0].split(\'/\');
  const board = [];
  for (const rank of ranks) {{
    const row = [];
    for (const ch of rank) {{
      if (/\\d/.test(ch)) row.push(...Array(+ch).fill(null));
      else {{
        const color = ch === ch.toUpperCase() ? \'w\' : \'b\';
        const piece = ch.toUpperCase();
        row.push(color + piece);
      }}
    }}
    board.push(row);
  }}
  return board;
}}

const PIECES = {{
  wK:\'\\u2654\',wQ:\'\\u2655\',wR:\'\\u2656\',wB:\'\\u2657\',wN:\'\\u2658\',wP:\'\\u2659\',
  bK:\'\\u265A\',bQ:\'\\u265B\',bR:\'\\u265C\',bB:\'\\u265D\',bN:\'\\u265E\',bP:\'\\u265F\',
}};

const SQ_SIZE = 50;
const FILES = \'abcdefgh\';

function drawBoard() {{
  const canvas = document.getElementById(\'board\');
  const ctx = canvas.getContext(\'2d\');
  const board = parseFen(FEN);
  const sz = SQ_SIZE;
  canvas.width  = sz * 8;
  canvas.height = sz * 8;
  const hlCol = \'rgba(255,235,0,0.52)\';

  for (let r = 0; r < 8; r++) {{
    for (let f = 0; f < 8; f++) {{
      const sqName = FILES[f] + (8 - r);
      ctx.fillStyle = (r + f) % 2 === 0 ? \'#f0d9b5\' : \'#b58863\';
      ctx.fillRect(f * sz, r * sz, sz, sz);
      if (HL.includes(sqName)) {{
        ctx.fillStyle = hlCol;
        ctx.fillRect(f * sz, r * sz, sz, sz);
      }}
      const piece = board[r][f];
      if (piece) {{
        const glyph = PIECES[piece];
        if (!glyph) continue;
        ctx.font = Math.floor(sz * 0.7) + \'px serif\';
        ctx.textAlign = \'center\';
        ctx.textBaseline = \'middle\';
        if (piece[0] === \'w\') {{
          ctx.strokeStyle = \'#555\';
          ctx.lineWidth = 3;
          ctx.strokeText(glyph, f * sz + sz/2, r * sz + sz/2);
        }}
        ctx.fillStyle = piece[0] === \'w\' ? \'#fff\' : \'#1a1a1a\';
        ctx.fillText(glyph, f * sz + sz/2, r * sz + sz/2);
      }}
    }}
  }}

  const ranks = document.getElementById(\'coord-ranks\');
  const files = document.getElementById(\'coord-files\');
  ranks.innerHTML = [8,7,6,5,4,3,2,1].map(n=>`<span style="height:${{sz}}px;display:flex;align-items:center">${{n}}</span>`).join(\'\');
  files.innerHTML = [...\'abcdefgh\'].map(c=>`<span style="width:${{sz}}px;display:inline-flex;justify-content:center">${{c}}</span>`).join(\'\');

  document.getElementById(\'to-move\').textContent = FEN.split(\' \')[1] === \'w\' ? \'White to move\' : \'Black to move\';
}}

drawBoard();

document.getElementById(\'dk\').onclick = function() {{
  const cur = document.documentElement.getAttribute(\'data-theme\');
  document.documentElement.setAttribute(\'data-theme\', cur === \'dark\' ? \'light\' : \'dark\');
  this.textContent = cur === \'dark\' ? \'Dark\' : \'Light\';
  drawBoard();
}};

let answered = false;
function pick(letter) {{
  if (answered) return;
  answered = true;
  [\'A\',\'B\',\'C\'].forEach(l => {{
    const el = document.getElementById(\'c\' + l);
    if (l === letter) el.classList.add(l === CORRECT ? \'correct\' : \'wrong\');
    if (l === CORRECT && l !== letter) el.classList.add(\'correct\');
  }});
  document.getElementById(letter === CORRECT ? \'v-ok\' : \'v-no\').style.display = \'block\';
  document.getElementById(\'more-btn\').style.display = \'inline-block\';
  try {{
    const data = JSON.parse(localStorage.getItem(DONE_KEY) || \'{{}}\');
    data[EX_KEY] = true;
    localStorage.setItem(DONE_KEY, JSON.stringify(data));
  }} catch(e) {{}}
}}

function showExplanation() {{
  document.getElementById(\'explanation\').style.display = \'block\';
  document.getElementById(\'more-btn\').style.display = \'none\';
}}
</script>
</body>
</html>
'''

# ── Helpers ──────────────────────────────────────────────────────────────────

def game_url(headers):
    """Build a chess.com search URL for the game using player names."""
    white = headers.get('White', '')
    black = headers.get('Black', '')
    date  = headers.get('Date', '').replace('.', '-')
    # chess.com game URLs aren't in the PGN; link to the event archive filtered by players
    if white and black:
        return (f"https://www.chess.com/games/search"
                f"?username={white}&opponent={black}&gameType=blitz")
    return 'https://www.chess.com/events/2026-titled-tuesday-blitz'

def nav_link(ex_num, total, direction):
    if direction == 'prev':
        if ex_num == 1: return ''
        return f'<a class="nav-btn" href="ex{ex_num-1:02d}.html">&larr; Prev</a>'
    else:
        if ex_num == total: return '<a class="nav-btn main" href="../index.html">Session &uarr;</a>'
        return f'<a class="nav-btn main" href="ex{ex_num+1:02d}.html">Next &rarr;</a>'

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 3:
        print("Usage: python3 generate_exercises.py <pgn_file> <session_slug>")
        sys.exit(1)

    pgn_path = sys.argv[1]
    session  = sys.argv[2]
    base_dir = os.path.join('training', session)

    print(f"Parsing {pgn_path}...")
    games = list(parse_pgn(pgn_path))
    print(f"Parsed {len(games)} games.")

    ex_global = 0
    for phase_idx, (phase_dir, phase_label, count, phase_id) in enumerate(PHASES):
        out_dir = os.path.join(base_dir, phase_dir)
        os.makedirs(out_dir, exist_ok=True)
        target_half = PHASE_HALF_MOVE[phase_dir]

        print(f"\n=== {phase_label} (target ~half-move {target_half}) ===")
        for i in range(count):
            ex_num = i + 1
            game_idx = ex_global % len(games)
            headers, moves = games[game_idx]
            ex_global += 1

            # Pick the target half-move (clamp to game length)
            t = min(target_half, len(moves) - 1)
            fen = replay_to_move(moves, t)

            white = headers.get('White', 'White')
            black = headers.get('Black', 'Black')
            welo  = headers.get('WhiteElo', '')
            belo  = headers.get('BlackElo', '')
            url   = game_url(headers)
            side  = 'White' if fen.split()[1] == 'w' else 'Black'

            players_str = f"{white} ({welo}) vs {black} ({belo})"
            title = f"{white} vs {black} — {phase_label}"

            html = EXERCISE_HTML.format(
                title        = title,
                session      = session,
                phase_label  = phase_label,
                ex_num       = f'{ex_num:02d}',
                ex_num_int   = ex_num,
                phase_id     = phase_id,
                players      = players_str,
                question     = f'{side} to move. What is the best plan here?',
                plan_a_title = 'Plan A — [to be filled]',
                plan_a_body  = 'Describe plan A.',
                plan_b_title = 'Plan B — [to be filled]',
                plan_b_body  = 'Describe plan B.',
                plan_c_title = 'Plan C — [to be filled]',
                plan_c_body  = 'Describe plan C.',
                correct      = 'A',
                explanation  = '<p>Explanation to be filled in.</p>',
                fen          = fen,
                hl           = '[]',
                game_url     = url,
                prev_link    = nav_link(ex_num, count, 'prev'),
                next_link    = nav_link(ex_num, count, 'next'),
            )

            out_path = os.path.join(out_dir, f'ex{ex_num:02d}.html')
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"  ex{ex_num:02d}: {white} vs {black}  move~{t//2}  side={side}")

    print("\nDone — 40 exercise stubs generated.")

if __name__ == '__main__':
    main()
