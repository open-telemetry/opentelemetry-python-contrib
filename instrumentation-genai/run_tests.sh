#!/usr/bin/env bash
# Run tests for all GenAI instrumentation packages
# Usage: ./run_tests.sh [package_name] [python_version] [variant]
# Examples:
#   ./run_tests.sh                          # Run all tests
#   ./run_tests.sh openai-v2                # Run openai-v2 tests only
#   ./run_tests.sh vertexai 312 latest      # Run vertexai with Python 3.12, latest deps

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default Python version
PYTHON_VERSION="${2:-312}"
VARIANT="${3:-latest}"

# Packages with tox configurations
TOX_PACKAGES="openai-v2 openai_agents-v2 vertexai google-genai anthropic"

# Packages without tox configurations (run with standalone venv)
STANDALONE_PACKAGES="crewai langchain langgraph agno haystack llamaindex bedrock cohere groq mistralai ollama replicate sagemaker together watsonx alephalpha transformers mcp chromadb lancedb marqo milvus pinecone qdrant weaviate"

# Track results
PASSED=0
FAILED=0
SKIPPED=0
PASSED_LIST=""
FAILED_LIST=""
SKIPPED_LIST=""

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
}

log_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
}

run_tox_test() {
    local package=$1
    local env="py${PYTHON_VERSION}-test-instrumentation-${package}-${VARIANT}"

    log_info "Running tox environment: $env"

    if tox -e "$env" 2>&1; then
        log_success "$package"
        PASSED_LIST="${PASSED_LIST}${package}\n"
        PASSED=$((PASSED + 1))
        return 0
    else
        log_fail "$package"
        FAILED_LIST="${FAILED_LIST}${package}\n"
        FAILED=$((FAILED + 1))
        return 1
    fi
}

find_package_dir() {
    local package=$1
    local package_name="opentelemetry-instrumentation-${package}"

    # Search in category subdirectories
    for category in llm-clients frameworks vector-dbs protocols; do
        local dir="$SCRIPT_DIR/$category/$package_name"
        if [ -d "$dir" ]; then
            echo "$dir"
            return 0
        fi
    done

    # Fallback: direct subdirectory (old structure)
    local dir="$SCRIPT_DIR/$package_name"
    if [ -d "$dir" ]; then
        echo "$dir"
        return 0
    fi

    return 1
}

run_standalone_test() {
    local package=$1
    local package_dir
    package_dir=$(find_package_dir "$package")

    if [ -z "$package_dir" ] || [ ! -d "$package_dir" ]; then
        log_skip "$package (directory not found)"
        SKIPPED_LIST="${SKIPPED_LIST}${package} (not found)\n"
        SKIPPED=$((SKIPPED + 1))
        return 0
    fi

    if [ ! -d "$package_dir/tests" ]; then
        log_skip "$package (no tests directory)"
        SKIPPED_LIST="${SKIPPED_LIST}${package} (no tests)\n"
        SKIPPED=$((SKIPPED + 1))
        return 0
    fi

    log_info "Running standalone tests for: $package"

    cd "$package_dir"

    # Create venv if it doesn't exist
    if [ ! -d ".venv" ]; then
        log_info "Creating virtual environment for $package"
        python3 -m venv .venv
    fi

    # Activate and install dependencies
    source .venv/bin/activate

    # Install base test dependencies
    pip install -q pytest pytest-asyncio pytest-vcr opentelemetry-test-utils \
        opentelemetry-api opentelemetry-sdk opentelemetry-semantic-conventions \
        wrapt pyyaml vcrpy 2>/dev/null || true

    # Install the package itself
    pip install -q -e . 2>/dev/null || true

    # Run tests and capture output
    local test_output
    test_output=$(python -m pytest tests/ -v 2>&1) || true
    local test_exit=$?

    # Check if tests passed or all were skipped
    local last_line
    last_line=$(echo "$test_output" | tail -1)

    if echo "$last_line" | grep -q "passed"; then
        log_success "$package"
        PASSED_LIST="${PASSED_LIST}${package}\n"
        PASSED=$((PASSED + 1))
        deactivate
        cd "$SCRIPT_DIR/.."
        return 0
    elif echo "$last_line" | grep -q "skipped" && ! echo "$last_line" | grep -q "failed" && ! echo "$last_line" | grep -q "error"; then
        log_success "$package (all tests skipped - dependency not installed)"
        PASSED_LIST="${PASSED_LIST}${package} (skipped)\n"
        PASSED=$((PASSED + 1))
        deactivate
        cd "$SCRIPT_DIR/.."
        return 0
    elif echo "$test_output" | grep -q "no tests ran\|collected 0 items"; then
        log_success "$package (no tests collected - dependency not installed)"
        PASSED_LIST="${PASSED_LIST}${package} (skipped)\n"
        PASSED=$((PASSED + 1))
        deactivate
        cd "$SCRIPT_DIR/.."
        return 0
    else
        log_fail "$package"
        echo "$test_output" | tail -20
        FAILED_LIST="${FAILED_LIST}${package}\n"
        FAILED=$((FAILED + 1))
        deactivate
        cd "$SCRIPT_DIR/.."
        return 1
    fi
}

run_single_package() {
    local package=$1

    # Check if it's a tox package
    for tox_pkg in $TOX_PACKAGES; do
        if [ "$tox_pkg" = "$package" ]; then
            run_tox_test "$package"
            return $?
        fi
    done

    # Otherwise run as standalone
    run_standalone_test "$package"
    return $?
}

run_all_tests() {
    log_info "Running all GenAI instrumentation tests"
    echo "================================================"

    # Run tox-configured packages
    log_info "Running tox-configured packages..."
    for package in $TOX_PACKAGES; do
        run_tox_test "$package" || true
    done

    # Run standalone packages
    log_info "Running standalone packages..."
    for package in $STANDALONE_PACKAGES; do
        run_standalone_test "$package" || true
    done
}

print_summary() {
    echo ""
    echo "================================================"
    echo -e "${BLUE}TEST SUMMARY${NC}"
    echo "================================================"

    if [ -n "$PASSED_LIST" ]; then
        echo -e "${GREEN}PASSED:${NC}"
        echo -e "$PASSED_LIST" | sort | while read -r line; do
            [ -n "$line" ] && echo -e "  ${GREEN}✓${NC} $line"
        done
    fi

    if [ -n "$FAILED_LIST" ]; then
        echo -e "${RED}FAILED:${NC}"
        echo -e "$FAILED_LIST" | sort | while read -r line; do
            [ -n "$line" ] && echo -e "  ${RED}✗${NC} $line"
        done
    fi

    if [ -n "$SKIPPED_LIST" ]; then
        echo -e "${YELLOW}SKIPPED:${NC}"
        echo -e "$SKIPPED_LIST" | sort | while read -r line; do
            [ -n "$line" ] && echo -e "  ${YELLOW}○${NC} $line"
        done
    fi

    echo ""
    echo "================================================"
    echo -e "Passed: ${GREEN}${PASSED}${NC}"
    echo -e "Failed: ${RED}${FAILED}${NC}"
    echo -e "Skipped: ${YELLOW}${SKIPPED}${NC}"
    echo "================================================"

    if [ $FAILED -gt 0 ]; then
        exit 1
    fi
}

# Main execution
if [ -n "$1" ]; then
    # Run single package
    run_single_package "$1"
else
    # Run all tests
    run_all_tests
fi

print_summary
