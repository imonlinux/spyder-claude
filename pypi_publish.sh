#!/bin/bash
# PyPI Publishing Script for spyder-claude
# This script builds and uploads the package to PyPI

set -e  # Exit on error

echo "📦 Building spyder-claude for PyPI..."

# Check prerequisites
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 not found. Please install Python 3.9+ first."
    exit 1
fi

if ! command -v git &> /dev/null; then
    echo "❌ git not found. Please install git first."
    exit 1
fi

# Install build tools
echo "📥 Installing build tools..."
python3 -m pip install --upgrade pip build twine

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf dist/ build/ *.egg-info

# Build the package
echo "🔨 Building package..."
python3 -m build

# Check the package
echo "🔍 Checking package with twine..."
python3 -m twine check dist/*

# Show what will be uploaded
echo "📋 Packages to upload:"
ls -lh dist/

# Ask for confirmation
echo ""
echo "⚠️  This will upload to PyPI. Make sure you have your credentials ready."
read -p "Continue with upload? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "📤 Uploading to PyPI..."
    python3 -m twine upload dist/*
    echo "✅ Upload complete!"
    echo ""
    echo "🎉 Users can now install with: pip install spyder-claude"
else
    echo "❌ Upload cancelled."
    exit 0
fi
