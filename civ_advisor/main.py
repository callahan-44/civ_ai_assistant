"""
Entry point for the Civ VI AI Advisor.
"""

from .gui import CivOverlay


def main():
    """Start the Civ VI AI Advisor overlay."""
    app = CivOverlay()
    app.run()


if __name__ == "__main__":
    main()
