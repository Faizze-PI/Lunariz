import re
from typing import List, Dict, Any, Optional
from lunariz.core.storage import Note


class MultiTokenSearch:
    @staticmethod
    def tokenize(text: str) -> List[str]:
        """Split text into lowercase alphanumeric tokens."""
        return [tok.lower() for tok in re.findall(r"\b[\w\-]+\b", text) if tok]

    @classmethod
    def score_note(cls, note: Note, tokens: List[str]) -> float:
        """Compute match score for a note against query tokens."""
        if not tokens:
            return 1.0

        title_lower = note.title.lower()
        content_lower = note.content.lower()
        tags_lower = [t.lower() for t in note.tags]

        score = 0.0
        all_matched = True

        for tok in tokens:
            tok_matched = False

            # Title matches (Highest priority)
            if tok in title_lower:
                score += 35.0
                tok_matched = True
                if re.search(r"\b" + re.escape(tok) + r"\b", title_lower):
                    score += 15.0  # Exact whole-word bonus

            # Tag matches (High priority)
            if any(tok == t for t in tags_lower):
                score += 25.0
                tok_matched = True
            elif any(tok in t for t in tags_lower):
                score += 12.0
                tok_matched = True

            # Content matches
            if tok in content_lower:
                score += 10.0
                tok_matched = True
                # Count frequency lightly (up to 5 occurrences)
                count = min(content_lower.count(tok), 5)
                score += (count * 2.0)

            if not tok_matched:
                all_matched = False

        # AND condition bonus: all tokens matched
        if all_matched:
            score += 50.0

        # Pinned notes bubble up
        if note.is_pinned:
            score += 15.0

        return score

    @classmethod
    def rank_notes(
        cls,
        notes: List[Note],
        query: str,
        tag_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[Note]:
        """Filter and rank notes based on query tokens."""
        clean_q = query.strip()
        tokens = cls.tokenize(clean_q)

        filtered = notes
        if tag_filter:
            tf = tag_filter.lstrip("#").lower()
            filtered = [n for n in filtered if tf in [t.lower() for t in n.tags]]

        if not tokens:
            # Sort by pinned then updated_at
            return sorted(filtered, key=lambda n: (n.is_pinned, n.updated_at), reverse=True)[:limit]

        scored: List[tuple[float, Note]] = []
        for note in filtered:
            s = cls.score_note(note, tokens)
            if s > 0:
                scored.append((s, note))

        scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [item[1] for item in scored[:limit]]
