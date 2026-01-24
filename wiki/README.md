# AceForge Wiki

This directory contains wiki documentation for the AceForge project.

## Wiki Home Page

The `Home.md` file in this directory contains the main wiki home page content for the AceForge repository. This page provides:

- **Installation instructions** - Pre-built releases and running from source
- **Launching guide** - First launch and subsequent launches
- **Basic workflows** - Step-by-step guides for common tasks
  - Generating your first track
  - Managing your music library
  - Adjusting vocal/instrumental balance
  - Saving and loading presets
  - Training custom LoRAs
  - Voice cloning
- **Generation settings** - Detailed explanations of all settings
- **Troubleshooting** - Common issues and solutions
- **Performance tips** - Optimizing for Apple Silicon

## Using This Content

To publish this content to the GitHub wiki:

1. Enable the wiki for the `audiohacking/AceForge` repository in GitHub settings
2. Clone the wiki repository:
   ```bash
   git clone https://github.com/audiohacking/AceForge.wiki.git
   ```
3. Copy `Home.md` to the wiki repository
4. Commit and push:
   ```bash
   cd AceForge.wiki
   git add Home.md
   git commit -m "Add comprehensive wiki home page"
   git push
   ```

## Content Source

The wiki content is extracted and synthesized from:
- `README.md` - Main project overview and quick start
- `USAGE.md` - Detailed user guide with comprehensive instructions

The wiki home page combines the most important information from both sources in a structured, easy-to-navigate format optimized for users looking for quick answers and step-by-step instructions.
