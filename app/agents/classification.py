"""
LinkedIn Post Classification Agent.

Determines whether a LinkedIn post represents an actual hiring
opportunity vs. a general discussion, old post, or irrelevant content.

This is critical because LinkedIn posts are informal — the system
must not treat every mention of "data engineer" as a job opening.
"""
from __future__ import annotations

import json
import google.generativeai as genai

from ..schemas import ClassificationResult, PostClassification
from ..utils.logger import get_logger

logger = get_logger("job_agent.classification")

CLASSIFICATION_PROMPT = """You are a LinkedIn post classifier. Analyze the given LinkedIn post and determine if it represents an active hiring opportunity.

CLASSIFICATION CATEGORIES:
- genuine_job: A clear job posting with role, requirements, and how to apply
- referral: Someone offering to refer candidates for a position
- walk_in: Walk-in interview or drive announcement
- campus_hiring: Campus recruitment or fresher drive
- recruiter_post: Recruiter posting about open positions
- general_discussion: Discussion about the industry, not a specific job
- expired: Post mentions a past deadline or the position is filled
- unclear: Cannot determine if this is a hiring opportunity

RULES:
1. Be conservative — if unsure, classify as "unclear"
2. Check for expiry signals: "position filled", "closed", dates in the past
3. Referral posts ARE valuable — someone offering to refer is actionable
4. Walk-in posts with dates in the past should be "expired"
5. Generic posts like "data engineers are in demand" are "general_discussion"

Return a valid JSON object:
{
    "classification": "one of the categories above",
    "is_hiring": true/false,
    "confidence": 0.0 to 1.0,
    "reasoning": "brief explanation"
}"""


class ClassificationAgent:
    """Classifies LinkedIn posts as hiring opportunities or not."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

    # Categories that should proceed in the pipeline
    ACTIONABLE_CATEGORIES = {
        PostClassification.GENUINE_JOB,
        PostClassification.REFERRAL,
        PostClassification.WALK_IN,
        PostClassification.CAMPUS_HIRING,
        PostClassification.RECRUITER_POST,
    }

    def classify(self, content: str, url: str = "") -> ClassificationResult:
        """
        Classify a single LinkedIn post.

        Args:
            content: The post text content.
            url: The post URL (for logging).

        Returns:
            ClassificationResult with category, is_hiring flag, and confidence.
        """
        try:
            prompt = (
                f"{CLASSIFICATION_PROMPT}\n\n"
                f"--- LINKEDIN POST ---\n"
                f"{content[:4000]}\n"
                f"--- END ---\n\n"
                f"Classify this post:"
            )

            response = self.model.generate_content(prompt)
            data = json.loads(response.text)
            result = ClassificationResult(**data)

            logger.info(
                f"Classified: [bold]{result.classification}[/] "
                f"(hiring={result.is_hiring}, conf={result.confidence:.0%})"
            )
            return result

        except Exception as e:
            logger.warning(f"Classification failed for {url}: {e}")
            return ClassificationResult(
                classification="unclear",
                is_hiring=False,
                confidence=0.0,
                reasoning=f"Classification error: {e}",
            )

    def is_actionable(self, result: ClassificationResult) -> bool:
        """Check if a classification result should proceed in the pipeline."""
        try:
            category = PostClassification(result.classification)
            return category in self.ACTIONABLE_CATEGORIES and result.is_hiring
        except ValueError:
            return False

    def classify_batch(
        self, posts: list[dict],
    ) -> list[tuple[dict, ClassificationResult]]:
        """
        Classify a batch of LinkedIn posts.

        Args:
            posts: List of dicts with 'content' and 'url' keys.

        Returns:
            List of (post_dict, ClassificationResult) tuples
            for posts that are actionable.
        """
        actionable = []

        for post in posts:
            result = self.classify(
                post.get("content", ""),
                post.get("url", ""),
            )
            if self.is_actionable(result):
                actionable.append((post, result))
            else:
                logger.info(
                    f"Skipped: {result.classification} — {result.reasoning[:80]}"
                )

        logger.info(
            f"Actionable LinkedIn posts: [bold]{len(actionable)}[/] / {len(posts)}"
        )
        return actionable
