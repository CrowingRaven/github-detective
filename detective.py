import argparse
import re
import requests
import datetime
from dateutil import parser as date_parser

def is_valid_github_url(url):
    """
    Validate if the provided URL is a valid GitHub repository URL.
    """
    # Regex pattern to match GitHub repo URLs of the form https://github.com/user/repo
    pattern = r"^https://github\.com/[^/]+/[^/]+/?$"
    return re.match(pattern, url) is not None

def analyze_bus_factor(repo_url, output_file=None):
    """
    Analyze the bus factor by fetching contributors and their commit counts.
    """
    print(f"Analyzing bus factor for {repo_url}...")

    # Assume repo_url is valid, extract owner and repo directly
    owner, repo = re.match(r"^https://github\.com/([^/]+)/([^/]+)/?$", repo_url).groups()
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contributors?per_page=100"

    try:
        response = requests.get(api_url)
        if response.status_code != 200:
            print(f"GitHub API error: {response.status_code} {response.reason}")
            return

        contributors = response.json()
        if not contributors:
            print("No contributors found.")
            return

        # Sort contributors by number of commits (descending)
        contributors.sort(key=lambda c: c.get("contributions", 0), reverse=True)
        total_commits = sum(c.get("contributions", 0) for c in contributors)
        output_lines = []
        output_lines.append(f"Total contributors: {len(contributors)}")
        output_lines.append("Top contributors:")
        for c in contributors[:5]:
            name = c.get("login", "unknown")
            commits = c.get("contributions", 0)
            percent = (commits / total_commits * 100) if total_commits else 0
            output_lines.append(f"  {name}: {commits} commits ({percent:.1f}%)")

        # Improved bus factor: minimal set of contributors covering >=60% of commits
        running = 0
        bus_factor = 0
        for c in contributors:
            running += c.get("contributions", 0)
            bus_factor += 1
            if running >= total_commits * 0.6:
                break
        percent_covered = (running / total_commits * 100) if total_commits else 0
        output_lines.append(f"Estimated bus factor: {bus_factor} (covers {percent_covered:.1f}% of commits)")
        output_lines.append("Bus factor group:")
        for c in contributors[:bus_factor]:
            output_lines.append(f"  {c.get('login', 'unknown')}")
        for line in output_lines:
            print(line)
        if output_file:
            with open(output_file, "a", encoding="utf-8") as f:
                f.write("Bus Factor Analysis\n")
                for line in output_lines:
                    f.write(line + "\n")
                f.write("\n")
    except Exception as e:
        print(f"Error during bus factor analysis: {e}")

def detect_stale_issues_prs(repo_url, output_file=None):
    """
    Detect stale issues and pull requests for the given repository.
    A stale issue/PR is one with no update in the last 60 days.
    """
    print(f"Detecting stale issues and PRs for {repo_url}...")

    # Assume repo_url is valid, extract owner and repo directly
    owner, repo = re.match(r"^https://github\.com/([^/]+)/([^/]+)/?$", repo_url).groups()
    headers = {"Accept": "application/vnd.github.v3+json"}
    stale_days = 60

    # Calculate cutoff datetime for staleness
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=stale_days)

    def fetch_stale(endpoint, item_type):
        # Fetch open issues or PRs and filter those not updated since cutoff
        url = f"https://api.github.com/repos/{owner}/{repo}/{endpoint}?state=open&per_page=100"
        try:
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                print(f"GitHub API error ({item_type}): {response.status_code} {response.reason}")
                return []
            items = response.json()
            stale = []
            for item in items:
                updated_at = item.get("updated_at") or item.get("created_at")
                if updated_at:
                    updated = date_parser.parse(updated_at)
                    if updated.tzinfo is None:
                        updated = updated.replace(tzinfo=datetime.UTC)
                    else:
                        updated = updated.astimezone(datetime.UTC)
                    if updated < cutoff:
                        stale.append(item)
            return stale
        except Exception as e:
            print(f"Error fetching {item_type}: {e}")
            return []

    stale_issues = fetch_stale("issues", "issues")
    # Exclude PRs from issues
    stale_issues = [i for i in stale_issues if "pull_request" not in i]
    stale_prs = fetch_stale("pulls", "pull requests")

    output_lines = []
    output_lines.append(f"Stale issues (> {stale_days} days inactive): {len(stale_issues)}")
    for issue in stale_issues[:5]:
        output_lines.append(f"  #{issue['number']}: {issue['title']} (last updated: {issue['updated_at']})")
    if len(stale_issues) > 5:
        output_lines.append(f"  ...and {len(stale_issues) - 5} more.")
    output_lines.append(f"Stale pull requests (> {stale_days} days inactive): {len(stale_prs)}")
    for pr in stale_prs[:5]:
        output_lines.append(f"  #{pr['number']}: {pr['title']} (last updated: {pr['updated_at']})")
    if len(stale_prs) > 5:
        output_lines.append(f"  ...and {len(stale_prs) - 5} more.")
    for line in output_lines:
        print(line)
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write("Stale Issues and PRs\n")
            for line in output_lines:
                f.write(line + "\n")
            f.write("\n")

def create_visualizations(repo_url, output_file=None):
    """
    Create visualizations of commit history and contributor networks.
    """
    print(f"Creating visualizations for {repo_url}...")

    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("matplotlib is required for visualizations. Please install it with 'pip install matplotlib'.")
        return

    # Assume repo_url is valid, extract owner and repo directly
    owner, repo = re.match(r"^https://github\.com/([^/]+)/([^/]+)/?$", repo_url).groups()
    headers = {"Accept": "application/vnd.github.v3+json"}

    print("Fetching commit history...")
    commits_url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=100"
    commit_dates = []
    page = 1
    while True:
        url = f"{commits_url}&page={page}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            print(f"GitHub API error (commits): {resp.status_code} {resp.reason}")
            break
        commits = resp.json()
        if not commits:
            break
        for commit in commits:
            date_str = commit.get("commit", {}).get("author", {}).get("date")
            if date_str:
                dt = date_parser.parse(date_str)
                if dt.tzinfo is not None:
                    dt = dt.astimezone(datetime.UTC)
                else:
                    dt = dt.replace(tzinfo=datetime.UTC)
                commit_dates.append(dt)
        # Limit to 10 pages to avoid excessive API calls
        if len(commits) < 100 or page >= 10: 
            break
        page += 1

    print("Fetching contributors...")
    contributors_url = f"https://api.github.com/repos/{owner}/{repo}/contributors?per_page=100"
    resp = requests.get(contributors_url, headers=headers)
    if resp.status_code != 200:
        print(f"GitHub API error (contributors): {resp.status_code} {resp.reason}")
        return
    contributors = resp.json()
    if not contributors:
        print("No contributor data available for visualization.")
        return

    from collections import Counter
    if commit_dates:
        # Group commits by month
        months = [dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0) for dt in commit_dates]
        month_counts = Counter(months)
        sorted_months = sorted(month_counts)
        counts = [month_counts[m] for m in sorted_months]
    else:
        sorted_months = []
        counts = []

    # Prepare top contributors data
    names = [c.get("login", "unknown") for c in contributors[:10]]
    commits = [c.get("contributions", 0) for c in contributors[:10]]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

    # Plot commits per month
    if sorted_months:
        ax1.plot(sorted_months, counts, marker='o')
        ax1.set_title("Commits per Month")
        ax1.set_xlabel("Month")
        ax1.set_ylabel("Number of Commits")
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax1.xaxis.set_major_locator(mdates.MonthLocator())
        ax1.set_xticks(sorted_months)
        ax1.set_xticklabels([m.strftime('%Y-%m') for m in sorted_months], rotation=45, ha='right')
    else:
        ax1.text(0.5, 0.5, "No commit data available", ha='center', va='center')
        ax1.set_title("Commits per Month")
        ax1.set_xlabel("Month")
        ax1.set_ylabel("Number of Commits")

    # Plot top contributors
    if names and commits:
        ax2.bar(names, commits, color='skyblue')
        ax2.set_title("Top Contributors")
        ax2.set_xlabel("Contributor")
        ax2.set_ylabel("Number of Commits")
        ax2.set_xticks(range(len(names)))
        ax2.set_xticklabels(names, rotation=45, ha='right')
    else:
        ax2.text(0.5, 0.5, "No contributor data available", ha='center', va='center')
        ax2.set_title("Top Contributors")
        ax2.set_xlabel("Contributor")
        ax2.set_ylabel("Number of Commits")

    plt.tight_layout()
    plt.show()
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write("Visualizations generated for repository: " + repo_url + "\n\n")

def main():
    # Argument parser for CLI usage
    parser = argparse.ArgumentParser(
        description="Analyze a GitHub repo: bus factor, stale issues/PRs, and visualizations."
    )
    parser.add_argument(
        "repo_url",
        help="GitHub repository URL (e.g., https://github.com/user/repo)"
    )
    parser.add_argument(
        "--bus-factor",
        action="store_true",
        help="Analyze bus factor"
    )
    parser.add_argument(
        "--stale",
        action="store_true",
        help="Detect stale issues/PRs"
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Create visualizations"
    )
    parser.add_argument(
        "--output-file",
        type=str,
        help="Write all output data to the specified text file"
    )

    args = parser.parse_args()

    if not is_valid_github_url(args.repo_url):
        print("Error: Invalid GitHub repository URL. Please use the format: https://github.com/user/repo")
        return

    ran_any = False
    if args.bus_factor:
        analyze_bus_factor(args.repo_url, args.output_file)
        ran_any = True
    if args.stale:
        detect_stale_issues_prs(args.repo_url, args.output_file)
        ran_any = True
    if args.visualize:
        create_visualizations(args.repo_url, args.output_file)
        ran_any = True

    # If no specific analysis is requested, run all
    if not ran_any:
        analyze_bus_factor(args.repo_url, args.output_file)
        detect_stale_issues_prs(args.repo_url, args.output_file)
        create_visualizations(args.repo_url, args.output_file)

if __name__ == "__main__":
    main()