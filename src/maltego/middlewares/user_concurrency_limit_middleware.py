# Copyright (c) Maltego Technologies GmbH.
from typing import Any, Dict, List, Literal, Optional, Union, Sequence
import logging
import time
import asyncio
from maltego.middlewares.middlewares import TransformMiddleware
from maltego.model.entity import MaltegoEntity
from maltego.model.context import MaltegoContext
from maltego.model.graph import MaltegoGraph
from maltego.model.transform import MaltegoTransform
from maltego.model.exception import MaltegoException
from maltego.model.types import MaltegoSettingTypes, ExecutionState

log = logging.getLogger(__name__)


class LimitExceededError(ValueError):
    pass


class BoundedSemaphoreWithMax(asyncio.BoundedSemaphore):
    def __init__(self, value: int = 1, *, max_waiters: Optional[int] = None):
        super().__init__(value=value)
        self.max_waiters = max_waiters

    async def acquire(self) -> Literal[True]:
        # _waiters is None before the semaphore is first contested (asyncio
        # initialises it lazily).  Guard defensively so we never raise
        # AssertionError; instead, treat a None deque as zero waiters.
        if self.max_waiters is not None and self.locked():
            waiters = self._waiters  # type: ignore[attr-defined]
            current_waiters = 0 if waiters is None else len(waiters)
            if current_waiters >= self.max_waiters:
                raise LimitExceededError(
                    "Too many waiters, must wait for some tasks to finish first.")
        return await super().acquire()


class UserConcurrencyLimitMiddleware(TransformMiddleware):
    class ConcurrencyLimitException(MaltegoException):
        def __init__(self, limiter_id: str, limitee: str) -> None:
            super().__init__(
                message="You're already running too many Transforms concurrently, please slow down.", code=429)
            self.limiter_id = limiter_id
            self.limitee = limitee

    def __init__(self, max_concurrent_transforms: int) -> None:
        self.max_concurrent_transforms = max_concurrent_transforms
        self._semaphores: Dict[str, BoundedSemaphoreWithMax] = {}
        self._id = str(time.time())

    async def before_transform(
            self,
            transform: MaltegoTransform,
            transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
            properties: Dict[str, MaltegoSettingTypes],
            context: MaltegoContext,
            soft_limit: int,
            hard_limit: int
    ) -> None:
        limit_key = f"{context.remote_ip}_{context.rate_limit_key or context.api_key}"
        sem = self._semaphores.get(limit_key)
        if sem is None:
            sem = BoundedSemaphoreWithMax(
                self.max_concurrent_transforms, max_waiters=0
            )
            self._semaphores[limit_key] = sem
        try:
            await sem.acquire()
        except LimitExceededError:
            raise self.ConcurrencyLimitException(
                limiter_id=self._id, limitee=limit_key)

    async def after_transform(
            self,
            transform: MaltegoTransform,
            transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
            output_entities: List[MaltegoEntity],
            context: MaltegoContext,
            state: ExecutionState,
            exceptions: Optional[Sequence[Exception]] = None,
    ) -> None:
        limit_key = f"{context.remote_ip}_{context.rate_limit_key or context.api_key}"
        if exceptions is not None:
            for ex in exceptions:
                if isinstance(ex, self.ConcurrencyLimitException) and ex.limiter_id == self._id:
                    # if this exception was thrown by us, we must not adjust the semaphore
                    # (it was never acquired).  Log a warning if the limit_key doesn't match
                    # instead of crashing with AssertionError.
                    if limit_key != ex.limitee:
                        log.warning(
                            "ConcurrencyLimitException limitee mismatch: expected %s, got %s",
                            ex.limitee, limit_key,
                        )
                    return
        sem = self._semaphores.get(limit_key)
        if sem is None:
            # Semaphore was already cleaned up (e.g. concurrent release race).
            # Nothing to release — log and return gracefully.
            log.warning("No semaphore found for limit_key %s in after_transform; skipping release.", limit_key)
            return
        sem.release()
        bound_value = getattr(sem, '_bound_value', None)
        sem_value = getattr(sem, '_value', None)
        if bound_value is None or sem_value is None:
            # Internal asyncio semaphore attributes unavailable — skip cleanup.
            log.warning("Semaphore internal state unavailable for limit_key %s; skipping cleanup.", limit_key)
            return
        if sem_value == bound_value:
            try:
                del self._semaphores[limit_key]
            except KeyError:
                pass
