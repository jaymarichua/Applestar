#!/usr/bin/env python3
# coding: utf-8

import os
import sys
import argparse
import torch

# Yanking in the Actor from our codebase. Adjust if your structure differs.
from distar.actor import Actor
from distar.ctools.utils import read_config

import warnings
warnings.filterwarnings(
    "ignore",
    message="Setting attributes on ParameterList is not supported."
)

# Load a default config as an alternative to read_config through user_config = load_default_config()
def load_default_config():
    """
    Returning a simple user_config so we have a baseline to work from.
    If you load from a file, tweak this accordingly.
    """
    return {
        "actor": {
            "model_paths": {
                "model1": "default",
                "model2": "default",
            },
            "use_mps": True, 
            "device": "mps",
            "player_ids": [],
        },
        "env": {
            "player_ids": []
        },
        "common": {
            "type": "play"
        }
    }

print("DEBUG: Running the updated play.py with --race support!")

def main():
    parser = argparse.ArgumentParser(
        description="Time to have a little fun with StarCraft II via Applestar, focusing on MPS."
    )
    parser.add_argument(
        "--model1",
        type=str,
        default=None,
        help="First model's name minus '.pth'. Defaults to 'default' if not given."
    )
    parser.add_argument(
        "--model2",
        type=str,
        default=None,
        help="Second model's name minus '.pth'. Defaults to 'default' if not given."
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU usage, ignoring MPS if it's available."
    )
    parser.add_argument(
        "--game_type",
        type=str,
        default="human_vs_agent",
        choices=["agent_vs_agent", "agent_vs_bot", "human_vs_agent"],
        help="Choose your match style. Default is 'human_vs_agent'."
    )

    # v0.1.1 Added single race argument with three valid choices, defaulting to 'zerg'.
    parser.add_argument(
        "--race",
        type=str,
        default="zerg",
        choices=["zerg", "protoss", "terran"],
        help="Which SC2 race to use for player side. Defaults to zerg."
    )

    args = parser.parse_args()

    # Ensure SC2PATH is found
    sc2path = os.environ.get("SC2PATH", "")
    if not sc2path:
        if sys.platform == "darwin":
            mac_default_sc2 = "/Applications/StarCraft II"
            if os.path.isdir(mac_default_sc2):
                os.environ["SC2PATH"] = mac_default_sc2
                print(f"[INFO] SC2PATH wasn't set, so I'm using {mac_default_sc2} by default.")
            else:
                raise EnvironmentError(
                    "SC2PATH is not set and StarCraft II wasn't found in /Applications/StarCraft II. "
                    "You'll need to install SC2 or manually specify SC2PATH."
                )
        else:
            raise EnvironmentError(
                "SC2PATH isn't set at all. You really need to point this to your StarCraft II installation."
            )
    else:
        if not os.path.isdir(sc2path):
            raise NotADirectoryError(
                f"SC2PATH is currently '{sc2path}', but there's no directory there. Check your install."
            )

    # Load user_config.yaml
    config_path = os.path.join(os.path.dirname(__file__), 'user_config.yaml')
    user_config = read_config(config_path)

    # Override for human player and real-time mode
    user_config.actor.job_type = "eval_test"
    user_config.common.type = "play"
    user_config.actor.episode_num = 1
    user_config.env.realtime = True

    # Override CUDA setting
    user_config["actor"]["use_cuda"] = False

    # Decide device: MPS > CUDA > CPU
    if args.cpu:
        print("[INFO] CPU mode only. MPS is sidelined.")
        user_config["actor"]["device"] = "cpu"
        user_config["actor"]["use_mps"] = False
        user_config["actor"]["use_cuda"] = False
    else:
        if torch.backends.mps.is_available():
            print("[INFO] MPS is alive and well, using Metal for acceleration!")
            user_config["actor"]["device"] = "mps"
            user_config["actor"]["use_mps"] = True
            user_config["actor"]["use_cuda"] = False
        elif torch.cuda.is_available():
            print("[WARNING] No MPS support found. Trying CUDA next. Check your Applestar version if CUDA is supported.")
            user_config["actor"]["device"] = "cuda"
            user_config["actor"]["use_mps"] = False
            user_config["actor"]["use_cuda"] = True
        else:
            print("[WARNING] No MPS support found. Falling back to CPU.")
            user_config["actor"]["device"] = "cpu"
            user_config["actor"]["use_mps"] = False
            user_config["actor"]["use_cuda"] = False

    # Model paths & checks
    default_model_path = os.path.join(os.path.dirname(__file__), "rl_model.pth")

    if args.model1 is not None:
        user_config["actor"]["model_paths"]["model1"] = os.path.join(
            os.path.dirname(__file__), args.model1 + ".pth"
        )
    model1 = user_config["actor"]["model_paths"]["model1"]
    if model1 == "default":
        model1 = default_model_path
        user_config["actor"]["model_paths"]["model1"] = model1

    if args.model2 is not None:
        user_config["actor"]["model_paths"]["model2"] = os.path.join(
            os.path.dirname(__file__), args.model2 + ".pth"
        )
    model2 = user_config["actor"]["model_paths"]["model2"]
    if model2 == "default":
        model2 = default_model_path
        user_config["actor"]["model_paths"]["model2"] = model2

    if not os.path.exists(model1):
        raise FileNotFoundError(f"[ERROR] Model1 is nowhere to be found at {model1}")
    if not os.path.exists(model2):
        raise FileNotFoundError(f"[ERROR] Model2 is nowhere to be found at {model2}")

    # v0.1.1 Override the first slot in user_config["env"]["races"]
    # so your player is Terran, Protoss, or Zerg as requested.
    user_config["env"]["races"][1] = args.race
    # The second entry (user_config["env"]["races"][1]) remains "zerg" by default

    # Game type logic
    if args.game_type == "agent_vs_agent":
        user_config["env"]["player_ids"] = [
            os.path.basename(model1).split(".")[0],
            os.path.basename(model2).split(".")[0],
        ]
    elif args.game_type == "agent_vs_bot":
        user_config["actor"]["player_ids"] = ["model1"]
        bot_level = "bot10"
        if args.model2 and "bot" in args.model2:
            bot_level = args.model2
        user_config["env"]["player_ids"] = [
            os.path.basename(model1).split(".")[0],
            bot_level
        ]
    elif args.game_type == "human_vs_agent":
        user_config["actor"]["player_ids"] = ["model1"]
        user_config["env"]["player_ids"] = [
            os.path.basename(model1).split(".")[0],
            "human"
        ]
    
    # Create Actor & Run
    actor = Actor(user_config)
    actor.run()

if __name__ == "__main__":
    main()

    # Parse logs to extract spam and toxic events
    spam_events, toxic_events = actor.parse_logs('path_to_log_file.log')
    print("Spam Events:", spam_events)
    print("Toxic Events:", toxic_events)

    # Summarize results from the result file
    actor.summarize_results('path_to_result_file.json')

