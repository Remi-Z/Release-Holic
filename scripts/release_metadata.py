"""Validate release refs and generate container release metadata using only the stdlib."""
import argparse
import json
import os
import re
from pathlib import Path

VERSION = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?")


def release_plan(repository, event, ref):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Expected a GitHub owner/repository name")
    trusted = event in {"push", "workflow_dispatch"}
    tag, prerelease = "", False
    if trusted and ref.startswith("refs/tags/"):
        tag = ref.removeprefix("refs/tags/")
        version = VERSION.fullmatch(tag)
        if not version or len(tag) > 128:
            raise ValueError("Release tags must be vMAJOR.MINOR.PATCH, optionally followed by a prerelease suffix")
        suffix = version[4]
        if suffix and any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in suffix.split(".")):
            raise ValueError("Numeric prerelease identifiers cannot have leading zeroes")
        prerelease = bool(suffix)
    publish = trusted and (ref == "refs/heads/main" or bool(tag))
    image_base = "ghcr.io/" + repository.lower()
    return {
        "backend_image": image_base + "-backend",
        "web_image": image_base + "-web",
        "publish": str(publish).lower(),
        "release": str(bool(tag)).lower(),
        "prerelease": str(prerelease).lower(),
        "tag": tag,
    }


def write_manifest(plan):
    if plan["publish"] != "true":
        raise ValueError("Cannot write a publication manifest for an untrusted ref")
    revision = os.environ["GITHUB_SHA"]
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Invalid commit revision")
    images = {}
    for component in ["backend", "web"]:
        digest = os.environ[component.upper() + "_DIGEST"]
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
            raise ValueError(f"Missing published {component} digest")
        image = plan[component + "_image"]
        images[component] = {"image": image, "digest": digest, "reference": image + "@" + digest, "commit_tag": image + ":sha-" + revision}
    manifest = {"repository": os.environ["GITHUB_REPOSITORY"], "commit": revision, "tag": plan["tag"] or "main", "images": images}
    Path("release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    notes = ["Container images", "", f"Source: https://github.com/{manifest['repository']}/commit/{revision}", ""]
    for component, image in images.items():
        notes.append(f"- {component}: `{image['reference']}`")
    notes.extend(["", "Both images passed the API, browser, and container stack checks. The backend image also runs the ingestion worker and scheduler.", "", "See the repository's container release instructions for Docker Compose setup.", ""])
    Path("release-notes.md").write_text("\n".join(notes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="GitHub Actions output file")
    parser.add_argument("--manifest", action="store_true")
    args = parser.parse_args()
    plan = release_plan(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REF"])
    if args.manifest:
        write_manifest(plan)
    elif args.output:
        with Path(args.output).open("a") as output:
            output.write("".join(f"{key}={value}\n" for key, value in plan.items()))
    else:
        print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
