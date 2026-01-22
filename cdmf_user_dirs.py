# cdmf_user_dirs.py

"""
OSX User Directories Management for AceForge

This module implements macOS conventions for storing user data:
- User Preferences: ~/Library/Preferences/com.aceforge.app/
- Application Data: ~/Library/Application Support/AceForge/

This ensures that user data persists across app updates and follows Apple's guidelines.
"""

from __future__ import annotations

from pathlib import Path
import sys
import shutil
import json
import os


def get_user_preferences_dir() -> Path:
    """
    Get the user preferences directory following OSX conventions.
    
    Returns:
        Path to ~/Library/Preferences/com.aceforge.app/
    """
    home = Path.home()
    prefs_dir = home / "Library" / "Preferences" / "com.aceforge.app"
    prefs_dir.mkdir(parents=True, exist_ok=True)
    return prefs_dir


def get_user_app_support_dir() -> Path:
    """
    Get the application support directory following OSX conventions.
    
    Returns:
        Path to ~/Library/Application Support/AceForge/
    """
    home = Path.home()
    app_support_dir = home / "Library" / "Application Support" / "AceForge"
    app_support_dir.mkdir(parents=True, exist_ok=True)
    return app_support_dir


def get_app_dir() -> Path:
    """
    Get the application directory (where the app bundle or script is located).
    
    This is used for:
    - Reading bundled resources (like presets.json)
    - Legacy path detection for migration
    """
    if getattr(sys, "frozen", False):
        # Running as frozen app (PyInstaller bundle)
        return Path(sys.executable).resolve().parent
    else:
        # Running from source
        return Path(__file__).parent.resolve()


def migrate_legacy_data() -> None:
    """
    Migrate data from the old APP_DIR-based storage to the new user directories.
    
    This function:
    1. Detects if data exists in the old location (APP_DIR)
    2. Migrates it to the appropriate user directories
    3. Leaves a marker file to prevent re-migration
    """
    app_dir = get_app_dir()
    prefs_dir = get_user_preferences_dir()
    support_dir = get_user_app_support_dir()
    
    # Check if migration has already been done
    migration_marker = prefs_dir / ".migration_complete"
    if migration_marker.exists():
        return
    
    print("[AceForge] Checking for legacy data to migrate...", flush=True)
    
    # Migrate configuration files to Preferences
    config_files = [
        "aceforge_config.json",
        "tracks_meta.json",
        "user_presets.json"
    ]
    
    for config_file in config_files:
        old_path = app_dir / config_file
        new_path = prefs_dir / config_file
        
        if old_path.exists() and not new_path.exists():
            try:
                shutil.copy2(old_path, new_path)
                print(f"[AceForge] Migrated {config_file} to user preferences", flush=True)
            except Exception as e:
                print(f"[AceForge] Warning: Failed to migrate {config_file}: {e}", flush=True)
    
    # Migrate data directories to Application Support
    data_dirs = [
        "generated",
        "training_datasets",
        "ace_training",
        "custom_lora",
        "training_config"
    ]
    
    for data_dir in data_dirs:
        old_path = app_dir / data_dir
        new_path = support_dir / data_dir
        
        if old_path.exists() and old_path.is_dir() and not new_path.exists():
            try:
                # Check if directory has content
                if any(old_path.iterdir()):
                    shutil.copytree(old_path, new_path, dirs_exist_ok=True)
                    print(f"[AceForge] Migrated {data_dir}/ to application support", flush=True)
                else:
                    # Just create empty directory
                    new_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"[AceForge] Warning: Failed to migrate {data_dir}: {e}", flush=True)
    
    # Migrate ace_models directory (special handling due to size)
    old_models = app_dir / "ace_models"
    new_models = support_dir / "ace_models"
    
    if old_models.exists() and old_models.is_dir() and not new_models.exists():
        try:
            # Check if there are actual model files (not just empty directories)
            has_models = any(
                f.is_file() and f.stat().st_size > 1024 * 1024  # Files larger than 1MB
                for f in old_models.rglob("*")
            )
            
            if has_models:
                print("[AceForge] Migrating model files (this may take a moment)...", flush=True)
                shutil.copytree(old_models, new_models, dirs_exist_ok=True)
                print("[AceForge] Model files migrated successfully", flush=True)
            else:
                # Just create the directory structure
                new_models.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[AceForge] Warning: Failed to migrate ace_models: {e}", flush=True)
            # Create empty directory as fallback
            new_models.mkdir(parents=True, exist_ok=True)
    
    # Handle aceforge_config.json special case: update models_folder path if it exists
    config_path = prefs_dir / "aceforge_config.json"
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                config = json.load(f)
            
            # If models_folder points to old APP_DIR location, update it
            if "models_folder" in config:
                old_models_path = Path(config["models_folder"])
                if old_models_path == old_models:
                    config["models_folder"] = str(new_models)
                    with config_path.open("w", encoding="utf-8") as f:
                        json.dump(config, f, indent=2)
                    print("[AceForge] Updated models folder path in config", flush=True)
        except Exception as e:
            print(f"[AceForge] Warning: Failed to update config: {e}", flush=True)
    
    # Copy bundled presets.json if it doesn't exist in preferences
    bundled_presets = app_dir / "presets.json"
    user_presets = prefs_dir / "presets.json"
    if bundled_presets.exists() and not user_presets.exists():
        try:
            shutil.copy2(bundled_presets, user_presets)
            print("[AceForge] Copied bundled presets to user preferences", flush=True)
        except Exception as e:
            print(f"[AceForge] Warning: Failed to copy presets: {e}", flush=True)
    
    # Create migration marker
    try:
        migration_marker.write_text(
            f"Migration completed on {Path(__file__).stat().st_mtime}\n"
        )
        print("[AceForge] Migration complete!", flush=True)
    except Exception as e:
        print(f"[AceForge] Warning: Failed to create migration marker: {e}", flush=True)


def ensure_user_directories() -> None:
    """
    Ensure all required user directories exist and run migration if needed.
    
    This should be called early in the application startup.
    """
    # First, ensure base directories exist
    prefs_dir = get_user_preferences_dir()
    support_dir = get_user_app_support_dir()
    
    # Run migration
    migrate_legacy_data()
    
    # Ensure all data directories exist
    data_dirs = [
        "generated",
        "training_datasets", 
        "ace_training",
        "custom_lora",
        "training_config",
        "ace_models"
    ]
    
    for data_dir in data_dirs:
        dir_path = support_dir / data_dir
        dir_path.mkdir(parents=True, exist_ok=True)
    
    # Ensure training_config has default_config.json
    default_config_path = support_dir / "training_config" / "default_config.json"
    if not default_config_path.exists():
        # Try to copy from bundled resources
        bundled_config = get_app_dir() / "training_config" / "default_config.json"
        if bundled_config.exists():
            try:
                shutil.copy2(bundled_config, default_config_path)
            except Exception as e:
                print(f"[AceForge] Warning: Failed to copy default training config: {e}", flush=True)
