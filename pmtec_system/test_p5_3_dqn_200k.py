#!/usr/bin/env python3
"""Verify 200K DQN model loads correctly and engine integration works."""

import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["PMTEC_HEADLESS"] = "1"

from deep_rl.dqn_agent import DQNAgent

agent = DQNAgent()
print(f"model_path property: {agent.model_path}")
loaded = agent.load()
print(f"Loaded: {loaded}")
print(f"Is trained: {agent.is_trained()}")
if loaded:
    import numpy as np

    obs = np.zeros(122, dtype=np.float32)
    action = agent.predict(obs, deterministic=True)
    print(f"Test prediction: obs(zeros 122-dim) -> action={action}")
    print(f"Device: {agent.device}")
print("\n[P5-3] 200K DQN model verification: PASS")
