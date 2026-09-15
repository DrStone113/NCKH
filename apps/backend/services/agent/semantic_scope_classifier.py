"""Local semantic intent classifier used by the hybrid scope router.

The adapter intentionally exposes the same small prediction contract as the
restricted JSON judge.  It receives only the current fragment and never has
access to chat history, profile data, RAG or tools.

This first version uses labelled Vietnamese prototypes over a compact
multilingual sentence encoder.  The confidence is a temperature-scaled routing
score, not a claim of statistical calibration; thresholds must be qualified on
the project's held-out OOS dataset before production rollout.
"""

from __future__ import annotations

import asyncio
import math
import threading
from collections.abc import Callable, Sequence
from typing import Any

from services.agent.scope_guard import (
    ScopeIntent,
    TopicPrediction,
    scope_for_intent,
)


_PROTOTYPES: dict[ScopeIntent, tuple[str, ...]] = {
    ScopeIntent.NUTRITION: (
        "Tôi nên ăn gì hôm nay?",
        "Món này có bao nhiêu calo và protein?",
        "Tôi vừa ăn một bát phở.",
        "Thực phẩm nào giàu chất xơ?",
        "Tôi có thể uống sữa này không?",
        "Cách nấu món ăn lành mạnh.",
    ),
    ScopeIntent.WEIGHT_MANAGEMENT: (
        "Tôi muốn giảm 2 kí trong 2 tháng.",
        "Mục tiêu của tôi là xuống 60 kg.",
        "Tôi muốn tăng cân an toàn.",
        "Làm sao giảm mỡ bụng?",
        "Tôi muốn giữ cân nặng hiện tại.",
        "Tôi muốn nhẹ hơn nhưng vẫn khỏe.",
        "toi muon giam beo trong 2 thang",
        "I want to lose fat in two months.",
        "Mình muốn lose weight trong hai tháng.",
    ),
    ScopeIntent.MEAL_PLANNING: (
        "Lập thực đơn giảm cân cho tôi.",
        "Tạo kế hoạch ăn uống bảy ngày.",
        "Đổi bữa tối trong kế hoạch dinh dưỡng.",
        "Thực đơn tuần này của tôi thế nào?",
        "Lên meal plan phù hợp với mục tiêu.",
    ),
    ScopeIntent.FITNESS: (
        "Gợi ý bài tập tại nhà.",
        "Lập lịch tập gym ba buổi mỗi tuần.",
        "Hôm nay tôi nên chạy bộ bao lâu?",
        "Bài tập nào tốt cho cơ chân?",
        "Tôi vừa hoàn thành bài workout.",
    ),
    ScopeIntent.HEALTH_PROFILE: (
        "Cập nhật chiều cao và cân nặng của tôi.",
        "Mục tiêu sức khỏe trong hồ sơ của tôi.",
        "Tôi bị dị ứng đậu phộng.",
        "Thay đổi mức độ vận động trong hồ sơ.",
        "Thông tin sức khỏe cá nhân của tôi.",
    ),
    ScopeIntent.APP_HEALTH_DATA: (
        "Ứng dụng hiển thị sai lượng kcal của tôi.",
        "Nhật ký hôm nay chưa có bữa sáng.",
        "Mở màn hình dinh dưỡng.",
        "Vì sao kế hoạch trong app không đúng ngày?",
        "Tôi muốn ghi bữa ăn này vào ứng dụng.",
    ),
    ScopeIntent.GENERAL_WELLNESS: (
        "Đêm qua tôi ngủ không ngon.",
        "Gần đây tôi thường xuyên căng thẳng.",
        "Tôi cảm thấy mệt mỏi cả ngày.",
        "Làm sao xây dựng thói quen khỏe mạnh?",
        "Chỉ số BMI của tôi có ổn không?",
    ),
    ScopeIntent.SAFETY_ESCALATION: (
        "Tôi bị đau ngực và khó thở.",
        "Tôi sắp ngất khi đang tập.",
        "Tôi bị phản vệ sau khi ăn.",
        "Tôi đã uống thuốc quá liều.",
        "Tôi đang nghĩ đến tự làm hại mình.",
    ),
    ScopeIntent.AMBIGUOUS: (
        "Bạn giúp tôi việc này được không?",
        "Cái này có ổn không?",
        "Tôi muốn thay đổi một chút.",
        "Giải thích thêm cho tôi.",
        "Tôi chưa biết nên làm thế nào.",
    ),
    ScopeIntent.OUT_OF_SCOPE: (
        "Viết code Python cho tôi.",
        "Giải phương trình toán học này.",
        "Dự báo thời tiết hôm nay.",
        "Dịch đoạn văn này sang tiếng Anh.",
        "Giá bitcoin ngày mai thế nào?",
        "Lên lịch trình du lịch Đà Nẵng.",
        "Viết một bài luận lịch sử.",
        "Kết quả trận bóng đá tối qua.",
    ),
}


class SemanticPrototypeScopeClassifier:
    """Classify intent locally with a lazily loaded sentence encoder."""

    def __init__(
        self,
        model_name: str,
        *,
        device: str | None = None,
        temperature: float = 0.06,
        full_confidence_similarity: float = 0.50,
        model_factory: Callable[..., Any] | None = None,
        prototypes: dict[ScopeIntent, tuple[str, ...]] | None = None,
    ) -> None:
        if not model_name.strip():
            raise ValueError("model_name is required")
        if temperature <= 0:
            raise ValueError("temperature must be positive")
        if not 0 < full_confidence_similarity <= 1:
            raise ValueError("full_confidence_similarity must be in (0, 1]")
        self.model_name = model_name
        self.device = device
        self.temperature = temperature
        self.full_confidence_similarity = full_confidence_similarity
        self._model_factory = model_factory
        self._prototypes = prototypes or _PROTOTYPES
        self._model: Any | None = None
        self._prototype_vectors: dict[ScopeIntent, list[list[float]]] | None = None
        self._load_lock = threading.Lock()
        self._batch_lock = asyncio.Lock()
        self._pending: list[tuple[str, asyncio.Future[TopicPrediction]]] = []
        self._batch_task: asyncio.Task[None] | None = None

    async def classify(self, text: str) -> TopicPrediction:
        if not isinstance(text, str) or not text.strip():
            return TopicPrediction(
                scope_for_intent(ScopeIntent.AMBIGUOUS),
                1.0,
                "EMPTY_INPUT",
                self.model_version,
                ScopeIntent.AMBIGUOUS,
            )
        loop = asyncio.get_running_loop()
        future: asyncio.Future[TopicPrediction] = loop.create_future()
        async with self._batch_lock:
            self._pending.append((text, future))
            if self._batch_task is None or self._batch_task.done():
                self._batch_task = asyncio.create_task(self._flush_batches())
        return await future

    async def _flush_batches(self) -> None:
        """Micro-batch only transient fragments: 5 ms, at most 16 each."""

        while True:
            await asyncio.sleep(0.005)
            async with self._batch_lock:
                batch = self._pending[:16]
                del self._pending[:16]
            if not batch:
                return
            texts = [item[0] for item in batch]
            try:
                predictions = await asyncio.to_thread(self._classify_many_sync, texts)
                for (_, future), prediction in zip(batch, predictions, strict=True):
                    if not future.done():
                        future.set_result(prediction)
            except Exception as exc:
                for _, future in batch:
                    if not future.done():
                        future.set_exception(exc)
            async with self._batch_lock:
                if not self._pending:
                    return

    async def prewarm(self) -> None:
        """Load the encoder and prototype matrix before serving chat traffic."""

        await asyncio.to_thread(self._ensure_loaded)

    @property
    def is_ready(self) -> bool:
        return self._model is not None and self._prototype_vectors is not None

    @property
    def model_version(self) -> str:
        return f"semantic-prototype-v1:{self.model_name}"

    def _classify_sync(self, text: str) -> TopicPrediction:
        return self._classify_many_sync([text])[0]

    def _classify_many_sync(self, texts: Sequence[str]) -> list[TopicPrediction]:
        model, prototype_vectors = self._ensure_loaded()
        query_vectors = self._encode(model, texts)
        return [
            self._prediction_from_vector(query_vector, prototype_vectors)
            for query_vector in query_vectors
        ]

    def _prediction_from_vector(
        self,
        query_vector: Sequence[float],
        prototype_vectors: dict[ScopeIntent, list[list[float]]],
    ) -> TopicPrediction:
        scores = {
            intent: max(self._dot(query_vector, vector) for vector in vectors)
            for intent, vectors in prototype_vectors.items()
        }
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        intent, _ = ranked[0]
        # The gate's primary decision is whether a fragment may enter the
        # health pipeline. Closely related health intents often share the
        # probability mass (for example weight management vs nutrition). Use
        # one maximum score per routing group so ALLOW_HEALTH does not gain an
        # artificial advantage merely because it contains more intent labels.
        # Absolute cosine strength then tempers confident-looking softmaxes on
        # unrelated text that is weakly similar to every prototype.
        group_scores: dict[str, float] = {}
        for candidate_intent, score in ranked:
            group = self._routing_group(candidate_intent)
            group_scores[group] = max(group_scores.get(group, -1.0), score)
        group_probabilities = self._softmax_probabilities(
            sorted(group_scores.values(), reverse=True)
        )
        semantic_strength = max(
            0.0,
            min(1.0, ranked[0][1] / self.full_confidence_similarity),
        )
        confidence = group_probabilities[0] * semantic_strength
        return TopicPrediction(
            scope_for_intent(intent),
            confidence,
            f"SEMANTIC_{intent.value}",
            self.model_version,
            intent,
        )

    def _ensure_loaded(self) -> tuple[Any, dict[ScopeIntent, list[list[float]]]]:
        with self._load_lock:
            if self._model is None:
                factory = self._model_factory
                if factory is None:
                    from sentence_transformers import SentenceTransformer

                    factory = SentenceTransformer
                kwargs = {"device": self.device} if self.device else {}
                self._model = factory(self.model_name, **kwargs)
            if self._prototype_vectors is None:
                intents: list[ScopeIntent] = []
                texts: list[str] = []
                for intent, examples in self._prototypes.items():
                    intents.extend([intent] * len(examples))
                    texts.extend(examples)
                encoded = self._encode(self._model, texts)
                grouped = {intent: [] for intent in self._prototypes}
                for intent, vector in zip(intents, encoded, strict=True):
                    grouped[intent].append(vector)
                self._prototype_vectors = grouped
            return self._model, self._prototype_vectors

    @staticmethod
    def _encode(model: Any, texts: Sequence[str]) -> list[list[float]]:
        encoded = model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(value) for value in vector] for vector in encoded]

    @staticmethod
    def _dot(left: Sequence[float], right: Sequence[float]) -> float:
        return sum(a * b for a, b in zip(left, right, strict=True))

    def _softmax_probabilities(self, scores: Sequence[float]) -> list[float]:
        highest = max(scores)
        weights = [math.exp((score - highest) / self.temperature) for score in scores]
        total = sum(weights)
        return [max(0.0, min(1.0, weight / total)) for weight in weights]

    @staticmethod
    def _routing_group(intent: ScopeIntent) -> str:
        scope = scope_for_intent(intent)
        if scope in {
            scope_for_intent(ScopeIntent.NUTRITION),
            scope_for_intent(ScopeIntent.WEIGHT_MANAGEMENT),
            scope_for_intent(ScopeIntent.MEAL_PLANNING),
            scope_for_intent(ScopeIntent.FITNESS),
            scope_for_intent(ScopeIntent.HEALTH_PROFILE),
            scope_for_intent(ScopeIntent.GENERAL_WELLNESS),
            scope_for_intent(ScopeIntent.SAFETY_ESCALATION),
        }:
            return "ALLOW_HEALTH"
        return intent.value


__all__ = ["SemanticPrototypeScopeClassifier"]
