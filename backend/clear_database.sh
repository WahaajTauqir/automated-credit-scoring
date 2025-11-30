#!/bin/bash

# Clear Database Shell Script Wrapper
# Convenient wrapper for the clear_database.py script

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Detect Python command
if command -v python &> /dev/null && python --version 2>&1 | grep -q "Python 3"; then
    PYTHON_CMD="python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo -e "${RED}❌ Error: Python 3 is not installed${NC}"
    exit 1
fi

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Parse arguments
case "$1" in
    --help|-h)
        echo "Clear Database Tool"
        echo ""
        echo "Usage:"
        echo "  ./clear_database.sh              # Interactive mode (asks for confirmation)"
        echo "  ./clear_database.sh --force      # Skip confirmation, delete all data"
        echo "  ./clear_database.sh --stats      # Show database statistics only"
        echo "  ./clear_database.sh --dataset ID # Delete specific dataset only"
        echo ""
        echo "Examples:"
        echo "  ./clear_database.sh              # Clear all data (with confirmation)"
        echo "  ./clear_database.sh --stats      # Check current data"
        echo "  ./clear_database.sh --dataset 1  # Delete dataset #1 only"
        echo ""
        exit 0
        ;;
    --stats)
        $PYTHON_CMD "$SCRIPT_DIR/clear_database.py" --stats
        ;;
    --force)
        echo -e "${YELLOW}⚠️  Force mode: Clearing all data without confirmation${NC}"
        $PYTHON_CMD "$SCRIPT_DIR/clear_database.py" --force
        ;;
    --dataset)
        if [ -z "$2" ]; then
            echo -e "${RED}❌ Error: --dataset requires an ID${NC}"
            echo "Usage: ./clear_database.sh --dataset ID"
            exit 1
        fi
        $PYTHON_CMD "$SCRIPT_DIR/clear_database.py" --dataset "$2"
        ;;
    "")
        # No arguments - interactive mode
        $PYTHON_CMD "$SCRIPT_DIR/clear_database.py"
        ;;
    *)
        echo -e "${RED}❌ Unknown option: $1${NC}"
        echo "Use --help for usage information"
        exit 1
        ;;
esac
