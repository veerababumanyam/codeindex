# Contributing to CodeIndex

Thank you for your interest in contributing to CodeIndex! We welcome contributions of all kinds, from bug fixes and documentation improvements to new features.

## Getting Started

1.  **Fork the repository** on GitHub.
2.  **Clone your fork** locally:
    ```bash
    git clone https://github.com/your-username/codeindex.git
    cd codeindex
    ```
3.  **Set up a development environment**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Or .venv\Scripts\Activate.ps1 on Windows
    pip install -e ".[analysis]"
    pip install pytest
    ```

## Development Workflow

-   **Create a branch** for your changes: `git checkout -b feature/my-new-feature`
-   **Write tests** for any new logic under the `tests/` directory.
-   **Run tests** using `pytest`:
    ```bash
    pytest
    ```
-   **Format your code** according to the existing style (4-space indentation, snake_case).

## Submitting a Pull Request

1.  **Push your changes** to your fork.
2.  **Open a Pull Request** against the `main` branch of the original repository.
3.  **Use the PR template** provided to describe your changes and verification steps.

## Code of Conduct

Please be respectful and collaborative. We aim to build a helpful and welcoming community for AI-augmented developers.
