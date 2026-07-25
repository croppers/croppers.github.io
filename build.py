import os
from html import escape
import json
import markdown
import yaml
from datetime import datetime
import shutil

def read_markdown_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split front matter and content
    parts = content.split('---', 2)
    if len(parts) >= 3:
        front_matter = yaml.safe_load(parts[1])
        markdown_content = parts[2]
    else:
        front_matter = {}
        markdown_content = content
    
    return front_matter, markdown_content

def convert_markdown_to_html(markdown_content):
    # Configure markdown with all necessary extensions
    md = markdown.Markdown(extensions=[
        'extra',  # Includes tables, footnotes, etc.
        'codehilite',  # Syntax highlighting
        'fenced_code',  # GitHub-style code blocks
        'tables',  # Tables support
        'attr_list',  # Attribute lists for HTML elements
        'def_list',  # Definition lists
        'abbr',  # Abbreviations
        'md_in_html'  # Markdown inside HTML
    ])
    return md.convert(markdown_content)

def copy_blog_images():
    # Create images directory in blog folder if it doesn't exist
    os.makedirs('blog/images', exist_ok=True)
    
    # Copy all images from content/blog/images to blog/images
    if os.path.exists('content/blog/images'):
        for filename in os.listdir('content/blog/images'):
            src = os.path.join('content/blog/images', filename)
            dst = os.path.join('blog/images', filename)
            shutil.copy2(src, dst)

def create_blog_post_html(front_matter, html_content, output_path):
    # Read the template
    with open('blog_template.html', 'r', encoding='utf-8') as f:
        template = f.read()
    
    # Format the date
    date = datetime.strptime(front_matter['date'], '%Y-%m-%d')
    formatted_date = date.strftime('%B %d, %Y')
    date_iso = date.date().isoformat()
    description = front_matter['description']
    slug = os.path.splitext(os.path.basename(output_path))[0]
    canonical = f'https://cropper.info/blog/{slug}.html'
    
    # Replace placeholders in template
    html = template.replace('{{title}}', escape(front_matter['title']))
    html = html.replace('{{description}}', escape(description))
    html = html.replace('{{canonical}}', escape(canonical))
    html = html.replace('{{date_iso}}', date_iso)
    html = html.replace('{{title_json}}', json.dumps(front_matter['title']))
    html = html.replace('{{description_json}}', json.dumps(description))
    html = html.replace('{{canonical_json}}', json.dumps(canonical))
    html = html.replace('{{date_iso_json}}', json.dumps(date_iso))
    html = html.replace('{{date}}', formatted_date)
    html = html.replace('{{content}}', html_content)
    
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Write the HTML file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

def build_blog():
    # Create blog directory if it doesn't exist
    os.makedirs('blog', exist_ok=True)
    
    # Copy images first
    copy_blog_images()
    
    # Process each markdown file
    for filename in sorted(os.listdir('content/blog')):
        if filename.endswith('.md'):
            input_path = os.path.join('content/blog', filename)
            output_path = os.path.join('blog', filename.replace('.md', '.html'))
            
            # Read and convert markdown
            front_matter, markdown_content = read_markdown_file(input_path)
            html_content = convert_markdown_to_html(markdown_content)
            
            # Create HTML file
            create_blog_post_html(front_matter, html_content, output_path)
            print(f'Built {output_path}')

if __name__ == '__main__':
    build_blog()
