"""Recreate the two fictional sample PDFs; requires requirements-dev.txt."""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'examples/content'
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='SampleLabel', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#53647c'), spaceAfter=18))
styles['Title'].textColor = colors.HexColor('#23374d')
styles['Title'].alignment = 0
styles['BodyText'].fontSize = 11
styles['BodyText'].leading = 17
styles['Heading2'].spaceBefore = 20

def document(filename, title, sections):
    path = OUT / filename
    flow = [Paragraph('FICTIONAL SAMPLE - REPLACE BEFORE PUBLISHING YOUR PORTFOLIO', styles['SampleLabel']),
            Paragraph(title, styles['Title']), Spacer(1, 8)]
    for heading, text in sections:
        flow += [Paragraph(heading, styles['Heading2']), Paragraph(text, styles['BodyText'])]
    def footer(canvas, doc):
        canvas.setTitle(title + ' - Fictional Sample')
        canvas.setAuthor('Web CV with Virtual-Me sample content')
        canvas.setSubject('Fictional demonstration document; no real personal information')
        canvas.setFont('Helvetica', 9)
        canvas.setFillColor(colors.HexColor('#53647c'))
        canvas.drawString(48, 32, 'Fictional example | example.com | No real person or employer')
        canvas.drawRightString(A4[0] - 48, 32, str(doc.page))
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=48, rightMargin=48, topMargin=44, bottomMargin=56).build(flow, onFirstPage=footer, onLaterPages=footer)

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    document('cv.pdf', 'Alex Morgan', [
        ('Software &amp; Data Engineer', 'alex@example.com | Your city, country'),
        ('Profile', 'Fictional example professional. I build useful software and dependable data workflows. Replace this sample with your own verified background and achievements.'),
        ('Experience', '<b>Software Engineer - Example Studio | 2024 - Present</b><br/>Built sample Python data-processing services and SQL reporting workflows. Collaborated with product teams, documented design decisions and improved automated checks.'),
        ('Example work project', '<b>Customer Insights Dashboard</b><br/>Implemented data cleaning and dashboard endpoints using sample service records. No production scale or measured business improvement is documented.'),
        ('Personal project', '<b>Community Events Explorer</b><br/>A React and TypeScript prototype for filtering fictional community events. Implemented filter controls and component tests. It is not a live ticketing service.'),
        ('Education', 'Your degree or qualification - Example University, 2023'),
        ('Skills', 'Python, TypeScript, React, SQL, API Design, Technical Writing, Collaboration'),
    ])
    document('events-project.pdf', 'Community Events Explorer', [
        ('Project overview', 'Fictional personal prototype by Alex Morgan. The application helps visitors find sample community events using category and date filters.'),
        ('Personal contribution', 'Implemented React components, TypeScript models, filter controls and component tests. Used a small fictional local dataset rather than a live third-party events API.'),
        ('Design decisions', 'Kept filtering deterministic and separated data access from presentation components. Added keyboard-accessible controls and explicit empty states.'),
        ('Scope and limitations', 'This is a demonstration prototype. No production deployment, user-study results, performance benchmark, revenue, attendance improvement or external partnership is documented. It does not process payments or sell tickets.'),
        ('Example stack', 'TypeScript, React, component testing, local JSON sample data'),
    ])
    print('Created two fictional example PDFs with neutral metadata.')

if __name__ == '__main__':
    main()
