#!/usr/bin/env python
"""Returns count of csv records wih Action Network tags

Looks for column `can2_user_tags`

email,can2_user_tags
some.one@example.com,"#Trump, ?Direct Action, ?Organizing, Phone_Bank"

Assume tags separated by ", " which misses some tags with embedded "," like
"[Alpine] Donors from 7.18.19 - 10.1.19 (Created: July 22, 2019 1:04 PM)"

"""
import csv
import sys

tag_count = {}
total = 0

if len(sys.argv) == 1:
    print("usage: count_tags [file ...] ")
    sys.exit(-1)

for filename in sys.argv[1:]:
    with open(filename, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            total += 1
            for tag in row['can2_user_tags'].split(", "):
                if tag:
                    tag_count[tag] = tag_count.get(tag, 0) + 1

tags_sorted = sorted(tag_count.items(),key=lambda x: x[1],reverse=True)

print("count,old,new")
for (tag, count) in tags_sorted:
    print(f"{count},{tag}")

print(f"{len(tags_sorted)},Tags in {total} items")
