#!/usr/bin/env python3
"""
Script to convert markdown CV to JSON format
Author: Yuan Chen
"""

import re
import json
import yaml
import argparse
from datetime import datetime, date
from pathlib import Path

# Custom JSON encoder to handle date objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

def parse_markdown_cv(md_file):
    """Parse the markdown CV file and extract sections."""
    content = Path(md_file).read_text(encoding='utf-8')
    content = re.sub(r'\A---\s*\n.*?\n---\s*\n', '', content, count=1, flags=re.DOTALL)

    # Accept both the setext headings used by cv.md and Markdown # headings.
    sections = {}
    current_section = None
    section_content = []
    lines = content.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        heading = re.match(r'^#{1,2}\s+(.+?)\s*#*$', line)
        if heading:
            section_name = heading.group(1)
        elif index + 1 < len(lines) and re.fullmatch(r'\s*=+\s*', lines[index + 1]):
            section_name = line.strip()
            index += 1
        else:
            section_name = None

        if section_name:
            if current_section:
                sections[current_section] = '\n'.join(section_content).strip()
            current_section = section_name
            section_content = []
        elif current_section:
            section_content.append(line)
        index += 1

    if current_section:
        sections[current_section] = '\n'.join(section_content).strip()
    return sections

def parse_config(config_file):
    """Parse the Jekyll _config.yml file for additional information."""
    if not config_file or not Path(config_file).exists():
        return {}
    
    with open(config_file, 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)
    
    return config or {}

def extract_author_info(config):
    """Extract author information from the config file."""
    author_info = {
        "name": config.get('name', ''),
        "email": "",
        "phone": "",
        "website": (str(config.get('url') or '').rstrip('/') + '/' +
                    str(config.get('baseurl') or '').strip('/')).rstrip('/'),
        "summary": "",
        "location": {
            "address": "",
            "postalCode": "",
            "city": "",
            "countryCode": "",
            "region": ""
        },
        "profiles": []
    }
    
    # Extract author details if available
    if 'author' in config:
        author = config.get('author', {})
        
        # Override name if author name is available
        if author.get('name'):
            author_info['name'] = author.get('name')
        
        # Add email
        if author.get('email'):
            author_info['email'] = author.get('email')

        if author.get('phone'):
            author_info['phone'] = author.get('phone')
        
        # Add location
        if author.get('location'):
            location = str(author['location'])
            city, separator, region = location.partition(',')
            author_info['location']['city'] = city.strip()
            if separator:
                author_info['location']['region'] = region.strip()

        # A student affiliation does not establish an employment relationship.
        if author.get('bio'):
            author_info['summary'] = author.get('bio')
        
        # Add social profiles
        profiles = []
        
        # Academic profiles
        if author.get('googlescholar'):
            profiles.append({
                "network": "Google Scholar",
                "username": "",
                "url": author.get('googlescholar')
            })
        
        if author.get('orcid'):
            profiles.append({
                "network": "ORCID",
                "username": "",
                "url": author.get('orcid')
            })
        
        if author.get('researchgate'):
            profiles.append({
                "network": "ResearchGate",
                "username": "",
                "url": author.get('researchgate')
            })
        
        # Social media profiles
        if author.get('github'):
            profiles.append({
                "network": "GitHub",
                "username": author.get('github'),
                "url": f"https://github.com/{author.get('github')}"
            })
        
        if author.get('linkedin'):
            profiles.append({
                "network": "LinkedIn",
                "username": author.get('linkedin'),
                "url": f"https://www.linkedin.com/in/{author.get('linkedin')}"
            })
        
        if author.get('twitter'):
            profiles.append({
                "network": "Twitter",
                "username": author.get('twitter'),
                "url": f"https://twitter.com/{author.get('twitter')}"
            })
        
        author_info['profiles'] = profiles
    
    return author_info

def top_level_bullets(text):
    """Group each unindented bullet with its indented detail and continuation lines."""
    entries = []
    for line in text.splitlines():
        match = re.match(r'^[*-]\s+(.+)$', line)
        if match:
            entries.append([match.group(1).strip()])
        elif entries and line.strip():
            entries[-1].append(line)
    return entries


def split_date_range(value):
    """Keep the CV's original date precision and expected/present qualifiers."""
    parts = re.split(r'\s+[–—-]\s+', value.strip(' *'), maxsplit=1)
    if len(parts) == 1:
        parts = re.split(r'(?<=\d{4})\s*[–—-]\s*(?=\d{4}|present\b)',
                         value.strip(' *'), maxsplit=1, flags=re.IGNORECASE)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else ('', parts[0].strip())


def parse_education(education_text):
    """Parse degree, institution, and dated entries without discarding qualifiers."""
    education_entries = []
    for entry in top_level_bullets(education_text):
        parts = [part.strip() for part in entry[0].split(',', 2)]
        if len(parts) != 3:
            continue
        degree, institution, dates = parts
        gpa_match = re.search(r'\bGPA:\s*([\d.]+)', '\n'.join(entry))
        dates = re.sub(r'\s*\bGPA:\s*[\d.]+', '', dates).strip()
        start_date, end_date = split_date_range(dates)
        education_entries.append({
            "institution": institution,
            "area": degree,
            "studyType": "",
            "startDate": start_date,
            "endDate": end_date,
            "gpa": gpa_match.group(1) if gpa_match else None,
            "courses": []
        })
    return education_entries


def parse_work_experience(work_text, research=False):
    """Parse either project-based research or the original position/company format."""
    work_entries = []
    for entry in top_level_bullets(work_text):
        heading = entry[0]
        # Research headings end in (*Month Year – Present*); old entries can
        # instead give position, company, and an unparenthesized year range.
        date_match = re.search(r'\s+\(\*?([^()]*\d{4}\s+[–—-]\s+[^()]*)\*?\)\s*$', heading)
        if date_match:
            heading = heading[:date_match.start()].strip()
            start_date, end_date = split_date_range(date_match.group(1))
        else:
            year_match = re.search(r'\b(\d{4}\s*[–—-]\s*(?:\d{4}|present))\b', heading, re.IGNORECASE)
            start_date, end_date = split_date_range(year_match.group(1)) if year_match else ('', '')
            if year_match:
                heading = heading[:year_match.start()].rstrip(' ,')

        details = []
        for line in entry[1:]:
            detail = re.match(r'^\s+[*-]\s+(.+)$', line)
            if detail:
                details.append(detail.group(1).strip())
            elif details and line.strip():
                details[-1] += ' ' + line.strip()

        supervisor = next((item for item in details if item.lower().startswith('supervisor:')), '')
        focus = next((item for item in details if item.lower().startswith('research focus:')), '')
        institution_match = re.search(r'\(([^()]*)\)\s*$', supervisor)
        company = institution_match.group(1).strip() if institution_match else ''
        if not research and ',' in heading:
            position, company = [part.strip() for part in heading.split(',', 1)]
        else:
            position = heading

        work_entries.append({
            "company": company,
            "position": position,
            "website": "",
            "startDate": start_date,
            "endDate": end_date,
            "summary": focus.partition(':')[2].strip() if focus else "",
            "highlights": [item for item in details if item != focus]
        })
    return work_entries

def parse_skills(skills_text):
    """Parse skills section from markdown."""
    skills_entries = []
    
    # Extract skill categories
    categories = re.findall(r'(?:^|\n)(\w+.*?):\s*(.*?)(?=\n\w+.*?:|\Z)', skills_text, re.DOTALL)
    
    for category, skills in categories:
        # Extract individual skills
        skill_list = [s.strip() for s in re.split(r',|\n', skills) if s.strip()]
        
        skills_entries.append({
            "name": category.strip(),
            "level": "",
            "keywords": skill_list
        })
    
    return skills_entries

def collection_front_matter(directory):
    """Yield visible collection metadata; hidden template examples stay hidden."""
    if not Path(directory).exists():
        return
    for item in sorted(Path(directory).glob('*.md')):
        content = item.read_text(encoding='utf-8')
        match = re.match(r'\A---\s*\n(.*?)\n---(?:\s*\n|\Z)', content, re.DOTALL)
        if not match:
            continue
        metadata = yaml.safe_load(match.group(1)) or {}
        if not isinstance(metadata, dict) or metadata.get('published') is False:
            continue
        yield metadata

def parse_publications(pub_dir):
    """Parse publications from the _publications directory."""
    publications = []
    for front_matter in collection_front_matter(pub_dir):
        publications.append({
            "name": front_matter.get('title', ''),
            "publisher": front_matter.get('venue', ''),
            "releaseDate": front_matter.get('date', ''),
            "website": front_matter.get('paperurl', ''),
            "summary": front_matter.get('excerpt', '')
        })
    return publications

def parse_talks(talks_dir):
    """Parse talks from the _talks directory."""
    talks = []
    for front_matter in collection_front_matter(talks_dir):
        talks.append({
            "name": front_matter.get('title', ''),
            "event": front_matter.get('venue', ''),
            "date": front_matter.get('date', ''),
            "location": front_matter.get('location', ''),
            "description": front_matter.get('excerpt', '')
        })
    return talks

def parse_teaching(teaching_dir):
    """Parse teaching from the _teaching directory."""
    teaching = []
    for front_matter in collection_front_matter(teaching_dir):
        teaching.append({
            "course": front_matter.get('title', ''),
            "institution": front_matter.get('venue', ''),
            "date": front_matter.get('date', ''),
            "role": front_matter.get('type', ''),
            "description": front_matter.get('excerpt', '')
        })
    return teaching

def parse_portfolio(portfolio_dir):
    """Parse portfolio items from the _portfolio directory."""
    portfolio = []
    for front_matter in collection_front_matter(portfolio_dir):
        portfolio.append({
            "name": front_matter.get('title', ''),
            "category": front_matter.get('collection', 'portfolio'),
            "date": front_matter.get('date', ''),
            "url": front_matter.get('permalink', ''),
            "description": front_matter.get('excerpt', '')
        })
    return portfolio

def create_cv_json(md_file, config_file, repo_root, output_file):
    """Create a JSON CV from markdown and other repository data."""
    # Parse the markdown CV
    sections = parse_markdown_cv(md_file)
    
    # Parse config file
    config = parse_config(config_file)
    
    # Extract author information
    author_info = extract_author_info(config)
    
    # Create the JSON structure
    cv_json = {
        "basics": author_info,
        "work": (parse_work_experience(sections.get('Research experience', ''), research=True) +
                 parse_work_experience(sections.get('Work experience', ''))),
        "education": parse_education(sections.get('Education', '')),
        "skills": parse_skills(sections.get('Skills', '')),
        "languages": [],
        "interests": [],
        "references": []
    }
    
    # Add publications
    cv_json["publications"] = parse_publications(Path(repo_root) / "_publications")
    
    # Add talks
    cv_json["presentations"] = parse_talks(Path(repo_root) / "_talks")
    
    # Add teaching
    cv_json["teaching"] = parse_teaching(Path(repo_root) / "_teaching")
    
    # Add portfolio
    cv_json["portfolio"] = parse_portfolio(Path(repo_root) / "_portfolio")
    
    # Extract languages and interests from config if available
    if 'languages' in config:
        cv_json["languages"] = config.get('languages', [])
    
    if 'interests' in config:
        cv_json["interests"] = config.get('interests', [])
    
    # Write the JSON to a file
    with open(output_file, 'w', encoding='utf-8') as file:
        json.dump(cv_json, file, indent=2, cls=DateTimeEncoder, ensure_ascii=False)
        file.write('\n')
    
    print(f"Successfully converted {md_file} to {output_file}")

def main():
    """Main function to parse arguments and run the conversion."""
    parser = argparse.ArgumentParser(description='Convert markdown CV to JSON format')
    parser.add_argument('--input', '-i', required=True, help='Input markdown CV file')
    parser.add_argument('--output', '-o', required=True, help='Output JSON file')
    parser.add_argument('--config', '-c', help='Jekyll _config.yml file')
    
    args = parser.parse_args()
    
    # Get repository root (parent directory of the input file's directory)
    repo_root = str(Path(args.input).parent.parent)
    
    create_cv_json(args.input, args.config, repo_root, args.output)

if __name__ == '__main__':
    main()
