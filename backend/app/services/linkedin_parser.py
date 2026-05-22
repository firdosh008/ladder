"""Parser for LinkedIn's official data export JSON.

LinkedIn's "Get a copy of your data" export provides profile data as JSON.
This module normalizes that JSON into dense, readable text ready for chunking
and embedding into the knowledge graph.

The parser handles multiple formats LinkedIn has used across export versions,
including flat top-level fields and nested profile wrappers.
"""

from __future__ import annotations

from typing import Any


def parse_linkedin_json(data: dict[str, Any]) -> str:
    """Parse a LinkedIn export JSON dict into a dense text block for embedding.

    Handles both the flat export format (fields at top level) and the nested
    format where profile data lives under a ``profile`` key.
    """
    # Some exports nest everything under a 'profile' key
    profile: dict[str, Any] = data.get("profile") or data
    if not isinstance(profile, dict):
        profile = data

    parts: list[str] = []

    # ── Identity ──
    name = _full_name(profile)
    headline = profile.get("headline") or ""
    parts.append(f"LinkedIn Profile: {name}")
    if headline:
        parts.append(f"Headline: {headline}")

    location = profile.get("location") or profile.get("geoLocationName") or ""
    if location:
        parts.append(f"Location: {location}")

    industry = profile.get("industry") or profile.get("industryName") or ""
    if industry:
        parts.append(f"Industry: {industry}")

    # ── About / Summary ──
    summary = profile.get("summary") or profile.get("about") or ""
    if summary:
        parts.append(f"\nAbout:\n{summary}")

    # ── Experience ──
    experience: list[dict[str, Any]] = _list(profile, "experience", "positions")
    if experience:
        parts.append("\nExperience:")
        for exp in experience:
            title = exp.get("title") or exp.get("position") or ""
            company = (
                exp.get("companyName")
                or exp.get("company")
                or _nested_str(exp, "company", "name")
                or ""
            )
            org = f" at {company}" if company else ""
            desc = exp.get("description") or exp.get("summary") or ""
            loc = exp.get("location") or exp.get("locationName") or ""
            loc_str = f" ({loc})" if loc else ""
            start = _date_str(exp, "startDate", "start")
            end = _date_str(exp, "endDate", "end")
            dates = f" ({start} — {end})" if start else ""

            line = f"- {title}{org}{loc_str}{dates}"
            parts.append(line)
            if desc:
                parts.append(f"  {desc[:500]}")

    # ── Education ──
    education: list[dict[str, Any]] = _list(profile, "education", "schools")
    if education:
        parts.append("\nEducation:")
        for edu in education:
            school = (
                edu.get("schoolName") or edu.get("school") or edu.get("name") or ""
            )
            degree = edu.get("degree") or edu.get("degreeName") or ""
            field = edu.get("fieldOfStudy") or edu.get("field") or ""
            degree_str = f"{degree} in {field}" if degree and field else (degree or field)
            start = _date_str(edu, "startDate", "start")
            end = _date_str(edu, "endDate", "end")
            years = f" ({start} — {end})" if start else ""
            parts.append(f"- {school}: {degree_str}{years}" if degree_str else f"- {school}{years}")

    # ── Skills ──
    skills: list[dict[str, Any]] = _list(profile, "skills", "skillItems")
    if skills:
        names: list[str] = []
        for s in skills[:50]:
            name = s.get("name") or s.get("skill") or ""
            if name:
                names.append(name)
        if names:
            parts.append(f"\nSkills: {', '.join(names)}")

    # ── Certifications ──
    certs: list[dict[str, Any]] = _list(profile, "certifications")
    if certs:
        parts.append("\nCertifications:")
        for cert in certs:
            name = cert.get("name") or ""
            authority = cert.get("authority") or cert.get("issuingOrganization") or ""
            auth_str = f" from {authority}" if authority else ""
            start = _date_str(cert, "startDate", "start")
            end = _date_str(cert, "endDate", "end")
            dates = f" ({start} — {end})" if start else ""
            url = cert.get("url") or cert.get("credentialUrl") or ""
            url_str = f" [{url}]" if url else ""
            parts.append(f"- {name}{auth_str}{dates}{url_str}")

    # ── Projects ──
    projects: list[dict[str, Any]] = _list(profile, "projects")
    if projects:
        parts.append("\nProjects:")
        for proj in projects:
            name = proj.get("title") or proj.get("name") or ""
            desc = (proj.get("description") or "")[:300]
            url = proj.get("url") or ""
            url_str = f" [{url}]" if url else ""
            parts.append(f"- {name}{url_str}")
            if desc:
                parts.append(f"  {desc}")

    # ── Publications ──
    pubs: list[dict[str, Any]] = _list(profile, "publications")
    if pubs:
        parts.append("\nPublications:")
        for pub in pubs:
            name = pub.get("name") or pub.get("title") or ""
            url = pub.get("url") or ""
            url_str = f" ({url})" if url else ""
            parts.append(f"- {name}{url_str}")

    # ── Honors & Awards ──
    honors: list[dict[str, Any]] = _list(profile, "honors", "awards")
    if honors:
        parts.append("\nHonors & Awards:")
        for h in honors:
            title = h.get("title") or h.get("name") or ""
            issuer = h.get("issuer") or h.get("issuingOrganization") or ""
            issuer_str = f" from {issuer}" if issuer else ""
            date = _date_str(h, "issueDate", "date")
            date_str = f" ({date})" if date else ""
            desc = (h.get("description") or "")[:200]
            parts.append(f"- {title}{issuer_str}{date_str}")
            if desc:
                parts.append(f"  {desc}")

    # ── Languages ──
    languages: list[dict[str, Any]] = _list(profile, "languages")
    if languages:
        items: list[str] = []
        for lang in languages[:20]:
            name = lang.get("name") or ""
            prof = lang.get("proficiency") or ""
            items.append(f"{name} ({prof})" if prof else name)
        if items:
            parts.append(f"\nLanguages: {', '.join(items)}")

    # ── Recommendations ──
    recs: list[dict[str, Any]] = _list(profile, "recommendations")
    if recs:
        parts.append("\nRecommendations:")
        for rec in recs:
            author = rec.get("recommender") or rec.get("author") or rec.get("name") or "Unknown"
            text = (rec.get("text") or rec.get("recommendationBody") or "")[:300]
            parts.append(f"- {author}: {text}")

    # ── Volunteer ──
    volunteer: list[dict[str, Any]] = _list(profile, "volunteer", "volunteerExperience")
    if volunteer:
        parts.append("\nVolunteer:")
        for vol in volunteer:
            role = vol.get("role") or vol.get("title") or ""
            org = vol.get("companyName") or vol.get("organization") or ""
            org_str = f" at {org}" if org else ""
            desc = (vol.get("description") or "")[:200]
            parts.append(f"- {role}{org_str}")
            if desc:
                parts.append(f"  {desc}")

    # ── Courses ──
    courses: list[dict[str, Any]] = _list(profile, "courses")
    if courses:
        names: list[str] = []
        for c in courses[:30]:
            name = c.get("name") or c.get("title") or ""
            if name:
                names.append(name)
        if names:
            parts.append(f"\nCourses: {', '.join(names)}")

    # ── Organizations ──
    orgs: list[dict[str, Any]] = _list(profile, "organizations")
    if orgs:
        items: list[str] = []
        for o in orgs[:20]:
            name = o.get("name") or o.get("organization") or ""
            role = o.get("title") or o.get("position") or ""
            if name:
                items.append(f"{name} ({role})" if role else name)
        if items:
            parts.append(f"\nOrganizations: {', '.join(items)}")

    return "\n".join(parts)


def parse_linkedin_json_files(files: dict[str, dict[str, Any]]) -> str:
    """Parse multiple LinkedIn export JSON files (e.g. Profile.json, Skills.json, etc.)

    Accepts a mapping of ``{filename: json_data}`` and merges all sections.
    """
    combined: dict[str, Any] = {}
    for filename, data in files.items():
        if not isinstance(data, dict):
            continue
        profile = data.get("profile") or data
        if isinstance(profile, dict):
            for key, value in profile.items():
                if key not in combined:
                    combined[key] = value
                elif isinstance(combined[key], list) and isinstance(value, list):
                    combined[key] = combined[key] + value
                elif isinstance(value, list):
                    combined[key] = value
                elif value:
                    combined[key] = combined[key] or value

    return parse_linkedin_json(combined)


# ─── helpers ────────────────────────────────────────────────────────────────────


def _full_name(data: dict[str, Any]) -> str:
    first = data.get("firstName") or data.get("first_name") or ""
    last = data.get("lastName") or data.get("last_name") or ""
    if first or last:
        return f"{first} {last}".strip()
    return data.get("name") or data.get("displayName") or "Unknown"


def _date_str(obj: dict[str, Any], *keys: str) -> str:
    for key in keys:
        val = obj.get(key)
        if isinstance(val, dict):
            y = val.get("year") or val.get("y")
            m = val.get("month") or val.get("m")
            if y:
                return f"{m}/{y}" if m else str(y)
        elif isinstance(val, str) and val.strip():
            return val.strip()
        elif isinstance(val, int) and val > 1900:
            return str(val)
    return ""


def _nested_str(obj: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        val = obj.get(key)
        if isinstance(val, dict):
            name = val.get("name") or val.get("title") or ""
            if name:
                return str(name)
        elif isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _list(data: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        val = data.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            items = val.get("items") or val.get("_list") or []
            if isinstance(items, list):
                return items
    return []
