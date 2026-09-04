import sys
from pathlib import Path

# Add backend/scripts to path
sys.path.insert(0, str(Path(__file__).parent))
from ingest import process_transcript, count_tokens

sample_dir = Path(__file__).parent.parent / "data" / "sample"
episodes = sorted([d for d in sample_dir.iterdir() if d.is_dir()])

print(f"Inspecting {len(episodes)} episodes...")
for ep in episodes:
    p = ep / "transcript.md"
    if not p.exists():
        continue
    meta, chunks = process_transcript(p)
    if not meta:
        continue
    total = len(chunks)
    guest = meta.guest or ep.name
    print(f"\n--- Episode: {guest} (Total chunks: {total}) ---")
    for idx, c in enumerate(chunks):
        t_count = count_tokens(c.chunk_text)
        is_last = (idx == total - 1)
        if t_count < 450 or t_count > 850:
            print(f"  Chunk {idx}/{total-1} (is_last={is_last}): {t_count} tokens | timestamp: {c.timestamp_ref}")
