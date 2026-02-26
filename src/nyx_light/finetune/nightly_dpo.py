"""
Nyx Light — Noćna DPO Optimizacija

Koristi odobrena knjiženja dana za fine-tuning modela.
Preference pairs: (odobreno=chosen, originalni_AI=rejected)

AXIOM: Samo odobrena knjiženja ulaze u trening set.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.finetune")


class NightlyDPOTrainer:
    """Noćni DPO trener za Nyx Light."""

    def __init__(self):
        self._training_runs = 0
        logger.info("NightlyDPOTrainer inicijaliziran")

    def collect_todays_pairs(self) -> List[Dict[str, Any]]:
        """Sakupi preference parove iz danas odobrenih knjiženja."""
        # TODO: Dohvati iz L1 epizodičke memorije
        return []

    async def train_nightly(self) -> Dict[str, Any]:
        """Pokreni noćni DPO trening."""
        pairs = self.collect_todays_pairs()
        if len(pairs) < 10:
            return {"status": "skipped", "reason": "Premalo parova (<10)"}

        self._training_runs += 1
        # TODO: MLX LoRA DPO training
        return {
            "status": "completed",
            "pairs_used": len(pairs),
            "run_number": self._training_runs,
        }
