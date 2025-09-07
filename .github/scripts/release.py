#!/usr/bin/env python3
import subprocess
import os


def sh(cmd, output=False):
    if isinstance(cmd, str):
        cmd_list = cmd.split()
    else:
        cmd_list = cmd

    if output:
        return subprocess.check_output(cmd_list).decode().strip()  # nosec B603
    else:
        subprocess.check_call(cmd_list)  # nosec B603


def main():
    ref_type = os.getenv("GITHUB_REF_TYPE", "")
    ref = os.getenv("GITHUB_REF", "")

    print(f"DEBUG: Ref type: {ref_type}")
    print(f"DEBUG: Ref: {ref}")

    if ref_type == "branch":
        print("🌿 Branch push detected, creating new tag...")

        print("🚀 Executing release workflow with Invoke...")
        sh(["python", "-m", "invoke", "release"])

        print("✅ Release workflow executed successfully!")

    elif ref_type == "tag":
        tag = ref.rsplit("/", 1)[-1]
        print(f"🏷️  Tag push detected: {tag}")

        print("🏗️  Building artifacts...")
        sh(["python", "-m", "invoke", "build-release", "--tag", tag])

        print("📦 Creating GitHub release...")
        sh(["python", "-m", "invoke", "create-release", "--tag", tag])

        print(f"✅ Release {tag} created successfully!")

    else:
        print(f"❓ Unknown ref type: {ref_type}")
        print("🚀 Executing default release workflow...")
        sh(["python", "-m", "invoke", "release"])


if __name__ == "__main__":
    main()
