import pytest
import numpy as np
from simulation.dogfight_gym_env import DogfightGymEnv


def test_gym_env_reset():
    env = DogfightGymEnv(discrete_actions=True, max_steps=100)
    obs, info = env.reset(seed=42)

    assert isinstance(obs, np.ndarray)
    assert obs.shape == (16,)
    assert info["step"] == 0
    assert info["successful_locks"] == 0


def test_gym_env_discrete_step():
    env = DogfightGymEnv(discrete_actions=True, max_steps=50)
    env.reset(seed=42)

    # Pure pursuit aksiyonu (0)
    obs, reward, terminated, truncated, info = env.step(0)

    assert isinstance(obs, np.ndarray)
    assert obs.shape == (16,)
    assert isinstance(reward, float)
    assert not terminated
    assert not truncated
    assert "distance_m" in info
    assert "ata_deg" in info


def test_gym_env_continuous_step():
    env = DogfightGymEnv(discrete_actions=False, max_steps=20)
    env.reset(seed=123)

    # Sürekli aksiyon [throttle=0.8, elevator=0.1, aileron=0.2]
    action = np.array([0.8, 0.1, 0.2], dtype=np.float32)
    obs, reward, terminated, truncated, info = env.step(action)

    assert obs.shape == (16,)
    assert info["distance_m"] > 0


def test_gym_env_geofence_penalty():
    env = DogfightGymEnv(discrete_actions=True)
    env.reset()
    # Mavi uçağı sahanın çok dışına ışınlayıp sınır cezasını doğrulayalım
    env.blue_aero.state.pos_n = 500.0
    env.blue_aero.state.pos_e = 500.0

    _, reward, terminated, _, _ = env.step(0)
    assert terminated
    assert reward < -100.0
