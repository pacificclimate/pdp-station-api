"""Development server entry point."""

import uvicorn


def main():
    uvicorn.run("pcds_dap.web:create_app", factory=True, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
