import os
import csv
import json
import argparse


def main(args):
    json_files = []

    for root, subdir, files in os.walk(args.json_directory):
        for f in files:
            if f.endswith(".json"):
                path = os.path.join(root, f)
                json_files.append(path)

    if not json_files:
        print("No JSON file is found under " + args.json_directory)
        return

    out = os.path.join(args.output_directory, args.output_name)
    with open(out, "w") as fd:
        header = set()
        rows = []
        for f in json_files:
            with open(f, "r") as in_fd:
                b = json.load(in_fd)

            row = {}
            for _, items in b.items():
                for key, val in items.items():
                    row[key] = val

            header = header.union(set(row.keys()))
            rows.append(row)

        writer = csv.DictWriter(fd, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Arguments for converting JSON result to CSV format"
    )
    parser.add_argument("--json-directory", type=str, default=os.path.curdir)
    parser.add_argument("--output-directory", type=str, default=os.path.curdir)
    parser.add_argument("--output-name", type=str, default="out.csv")
    args = parser.parse_args()
    main(args)
