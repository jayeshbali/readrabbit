"""
Tests for recommendation_engine.py

All tests use fake in-memory data — no database or API calls needed.
Run with: pytest tests/test_recommendation_engine.py -v
"""

import math
from datetime import datetime, timedelta
from recommendation_engine import (
    cosine_similarity,
    calculate_recency_weight,
    is_research_paper,
    cluster_by_topics,
    build_interest_clusters,
    build_user_profile,
    calculate_dismissed_penalty,
    enforce_topic_diversity,
    get_recommendations,
    get_similar_articles,
    extract_user_interests,
    InterestCluster,
)


# ============== Helpers ==============

def make_embedding(value: float, dims: int = 4) -> list:
    """Create a simple unit vector for testing."""
    vec = [0.0] * dims
    vec[0] = value
    magnitude = math.sqrt(sum(v * v for v in vec))
    return [v / magnitude for v in vec] if magnitude > 0 else vec


def make_article(id: str, topics: list, embedding=None, url: str = None, source: str = "", title: str = "", saved_at=None):
    return {
        "id": id,
        "title": title or f"Article {id}",
        "url": url or f"https://example.com/{id}",
        "source": source,
        "topics": topics,
        "embedding": embedding or make_embedding(0.5),
        "saved_at": saved_at,
    }


# ============== cosine_similarity ==============

class TestCosineSimilarity:
    def test_identical_vectors(self):
        vec = [1.0, 0.0, 0.0]
        assert cosine_similarity(vec, vec) == 1.0

    def test_opposite_vectors(self):
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == -1.0

    def test_perpendicular_vectors(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_mismatched_lengths_returns_zero(self):
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0

    def test_empty_vectors_return_zero(self):
        assert cosine_similarity([], []) == 0.0

    def test_zero_vector_returns_zero(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


# ============== calculate_recency_weight ==============

class TestRecencyWeight:
    def test_today_is_close_to_one(self):
        weight = calculate_recency_weight(datetime.utcnow())
        assert weight > 0.9

    def test_30_days_ago_is_half(self):
        saved_at = datetime.utcnow() - timedelta(days=30)
        weight = calculate_recency_weight(saved_at)
        assert abs(weight - 0.5) < 0.05

    def test_60_days_ago_is_quarter(self):
        saved_at = datetime.utcnow() - timedelta(days=60)
        weight = calculate_recency_weight(saved_at)
        assert abs(weight - 0.25) < 0.05

    def test_very_old_article_has_minimum_weight(self):
        saved_at = datetime.utcnow() - timedelta(days=365)
        weight = calculate_recency_weight(saved_at)
        assert weight == 0.1  # minimum floor

    def test_none_returns_default(self):
        weight = calculate_recency_weight(None)
        assert weight == 0.5

    def test_recent_is_heavier_than_old(self):
        recent = calculate_recency_weight(datetime.utcnow() - timedelta(days=5))
        old = calculate_recency_weight(datetime.utcnow() - timedelta(days=90))
        assert recent > old


# ============== is_research_paper ==============

class TestIsResearchPaper:
    def test_arxiv_url(self):
        assert is_research_paper("https://arxiv.org/abs/2301.00001") is True

    def test_normal_blog_url(self):
        assert is_research_paper("https://paulgraham.com/essays/startups.html") is False

    def test_source_with_journal(self):
        assert is_research_paper("https://example.com", source="Journal of Machine Learning") is True

    def test_title_with_et_al(self):
        assert is_research_paper("https://example.com", title="Smith et al. propose a new method") is True

    def test_regular_article(self):
        assert is_research_paper("https://fs.blog/mental-models", source="Farnam Street", title="Mental Models") is False

    def test_pubmed_url(self):
        assert is_research_paper("https://pubmed.ncbi.nlm.nih.gov/12345") is True


# ============== cluster_by_topics ==============

class TestClusterByTopics:
    def test_groups_by_first_topic(self):
        articles = [
            make_article("1", ["AI", "Tech"]),
            make_article("2", ["AI", "Startups"]),
            make_article("3", ["Philosophy"]),
        ]
        clusters = cluster_by_topics(articles)
        assert len(clusters["AI"]) == 2
        assert len(clusters["Philosophy"]) == 1

    def test_no_topics_goes_to_general(self):
        articles = [make_article("1", [])]
        clusters = cluster_by_topics(articles)
        assert "General" in clusters

    def test_empty_list(self):
        assert cluster_by_topics([]) == {}


# ============== build_interest_clusters ==============

class TestBuildInterestClusters:
    def test_creates_cluster_per_topic(self):
        articles = [
            make_article("1", ["AI"], make_embedding(0.9)),
            make_article("2", ["AI"], make_embedding(0.8)),
            make_article("3", ["Philosophy"], make_embedding(0.1)),
        ]
        clusters = build_interest_clusters(articles)
        topic_names = [c.name for c in clusters]
        assert "AI" in topic_names
        assert "Philosophy" in topic_names

    def test_skips_articles_without_embeddings(self):
        articles = [
            make_article("1", ["AI"], embedding=None),
            make_article("2", ["AI"], make_embedding(0.5)),
        ]
        clusters = build_interest_clusters(articles)
        # Should still create cluster from article with embedding
        assert len(clusters) == 1

    def test_empty_articles_returns_empty(self):
        assert build_interest_clusters([]) == []

    def test_centroid_is_average_of_embeddings(self):
        emb1 = [1.0, 0.0, 0.0, 0.0]
        emb2 = [0.0, 1.0, 0.0, 0.0]
        articles = [
            make_article("1", ["AI"], emb1),
            make_article("2", ["AI"], emb2),
        ]
        clusters = build_interest_clusters(articles)
        centroid = clusters[0].embedding
        assert abs(centroid[0] - 0.5) < 0.001
        assert abs(centroid[1] - 0.5) < 0.001

    def test_sorted_by_score_descending(self):
        articles = [
            make_article("1", ["Niche"], make_embedding(0.5)),
            make_article("2", ["AI"], make_embedding(0.5)),
            make_article("3", ["AI"], make_embedding(0.6)),
            make_article("4", ["AI"], make_embedding(0.7)),
        ]
        clusters = build_interest_clusters(articles)
        # AI cluster (3 articles) should rank higher than Niche (1 article)
        assert clusters[0].name == "AI"


# ============== build_user_profile ==============

class TestBuildUserProfile:
    def test_saved_ids_are_tracked(self):
        articles = [make_article("a1", ["AI"]), make_article("a2", ["Tech"])]
        profile = build_user_profile(articles)
        assert "a1" in profile.saved_article_ids
        assert "a2" in profile.saved_article_ids

    def test_dismissed_ids_are_tracked(self):
        saved = [make_article("s1", ["AI"])]
        dismissed = [make_article("d1", ["Spam"])]
        profile = build_user_profile(saved, dismissed)
        assert "d1" in profile.dismissed_article_ids

    def test_topic_counts_are_correct(self):
        articles = [
            make_article("1", ["AI", "Tech"]),
            make_article("2", ["AI"]),
        ]
        profile = build_user_profile(articles)
        assert profile.topic_counts["AI"] == 2
        assert profile.topic_counts["Tech"] == 1

    def test_dismissed_embeddings_collected(self):
        saved = [make_article("s1", ["AI"], make_embedding(0.9))]
        dismissed = [make_article("d1", ["Spam"], make_embedding(0.1))]
        profile = build_user_profile(saved, dismissed)
        assert len(profile.dismissed_embeddings) == 1


# ============== calculate_dismissed_penalty ==============

class TestDismissedPenalty:
    def test_no_dismissed_returns_one(self):
        penalty = calculate_dismissed_penalty(make_embedding(0.5), [])
        assert penalty == 1.0

    def test_very_similar_to_dismissed_gets_heavy_penalty(self):
        vec = [1.0, 0.0, 0.0, 0.0]
        penalty = calculate_dismissed_penalty(vec, [vec])
        assert penalty == 0.3

    def test_unrelated_to_dismissed_gets_no_penalty(self):
        article = [1.0, 0.0, 0.0, 0.0]
        dismissed = [[0.0, 1.0, 0.0, 0.0]]
        penalty = calculate_dismissed_penalty(article, dismissed)
        assert penalty == 1.0


# ============== enforce_topic_diversity ==============

class TestTopicDiversity:
    def test_limits_per_topic(self):
        articles = [
            make_article("1", ["AI"]),
            make_article("2", ["AI"]),
            make_article("3", ["AI"]),
            make_article("4", ["Philosophy"]),
        ]
        result = enforce_topic_diversity(articles, max_per_topic=2, total_count=4)
        ai_count = sum(1 for a in result if a["topics"][0] == "AI")
        assert ai_count <= 2

    def test_respects_total_count(self):
        articles = [make_article(str(i), ["AI"]) for i in range(10)]
        result = enforce_topic_diversity(articles, max_per_topic=5, total_count=3)
        assert len(result) <= 3

    def test_empty_input(self):
        assert enforce_topic_diversity([], max_per_topic=2, total_count=4) == []


# ============== get_recommendations ==============

class TestGetRecommendations:
    def _make_profile(self, topics=("AI",)):
        saved = [make_article(f"saved_{i}", [t], make_embedding(0.9)) for i, t in enumerate(topics)]
        return build_user_profile(saved)

    def test_returns_correct_count(self):
        profile = self._make_profile(["AI", "Philosophy"])
        candidates = [make_article(str(i), ["Tech"], make_embedding(0.5)) for i in range(10)]
        recs = get_recommendations(profile, candidates, count=4)
        assert len(recs) <= 4

    def test_never_recommends_saved_articles(self):
        profile = self._make_profile(["AI"])
        saved_ids = list(profile.saved_article_ids)
        candidates = [make_article(id, ["AI"], make_embedding(0.9)) for id in saved_ids]
        recs = get_recommendations(profile, candidates, count=4)
        rec_ids = {r["id"] for r in recs}
        assert rec_ids.isdisjoint(profile.saved_article_ids)

    def test_never_recommends_dismissed_articles(self):
        saved = [make_article("s1", ["AI"], make_embedding(0.9))]
        dismissed = [make_article("d1", ["AI"], make_embedding(0.9))]
        profile = build_user_profile(saved, dismissed)
        candidates = dismissed + [make_article("c1", ["AI"], make_embedding(0.5))]
        recs = get_recommendations(profile, candidates, count=4)
        rec_ids = {r["id"] for r in recs}
        assert "d1" not in rec_ids

    def test_never_recommends_research_papers(self):
        profile = self._make_profile(["AI"])
        candidates = [
            make_article("paper1", ["AI"], make_embedding(0.9), url="https://arxiv.org/abs/1234"),
            make_article("blog1", ["AI"], make_embedding(0.9), url="https://paulgraham.com/ai"),
        ]
        recs = get_recommendations(profile, candidates, count=4)
        rec_ids = {r["id"] for r in recs}
        assert "paper1" not in rec_ids

    def test_no_profile_clusters_returns_random(self):
        # User with no embeddings → no clusters → random picks
        saved = [{"id": "s1", "topics": ["AI"], "embedding": None}]
        profile = build_user_profile(saved)
        candidates = [make_article(str(i), ["Tech"]) for i in range(5)]
        recs = get_recommendations(profile, candidates, count=3)
        assert len(recs) <= 3

    def test_recommendation_type_field_present(self):
        profile = self._make_profile(["AI"])
        candidates = [make_article(str(i), ["AI"], make_embedding(0.6)) for i in range(10)]
        recs = get_recommendations(profile, candidates, count=4)
        for rec in recs:
            assert rec.get("recommendation_type") in ("on_topic", "serendipity")


# ============== get_similar_articles ==============

class TestGetSimilarArticles:
    def test_returns_similar_not_self(self):
        article = make_article("target", ["AI"], [1.0, 0.0, 0.0, 0.0])
        candidates = [
            make_article("similar", ["AI"], [0.9, 0.1, 0.0, 0.0]),
            make_article("target", ["AI"], [1.0, 0.0, 0.0, 0.0]),  # self
        ]
        results = get_similar_articles(article, candidates, count=4)
        ids = [r["id"] for r in results]
        assert "target" not in ids
        assert "similar" in ids

    def test_excludes_specified_ids(self):
        article = make_article("target", ["AI"], [1.0, 0.0, 0.0, 0.0])
        candidates = [make_article("excluded", ["AI"], [0.9, 0.1, 0.0, 0.0])]
        results = get_similar_articles(article, candidates, count=4, exclude_ids={"excluded"})
        assert results == []

    def test_no_embedding_returns_empty(self):
        article = make_article("target", ["AI"], embedding=None)
        candidates = [make_article("c1", ["AI"], make_embedding(0.5))]
        assert get_similar_articles(article, candidates) == []


# ============== extract_user_interests ==============

class TestExtractUserInterests:
    def test_returns_top_n_topics(self):
        articles = [
            make_article("1", ["AI"]),
            make_article("2", ["AI"]),
            make_article("3", ["Philosophy"]),
        ]
        profile = build_user_profile(articles)
        interests = extract_user_interests(profile, top_n=2)
        assert interests[0] == "AI"
        assert len(interests) <= 2

    def test_empty_profile_returns_empty(self):
        profile = build_user_profile([])
        assert extract_user_interests(profile) == []
