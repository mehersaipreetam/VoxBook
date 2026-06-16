import fitz

def create_pdf(filename="test_book.pdf"):
    doc = fitz.open()
    
    # Page 1: Title and TOC
    page = doc.new_page()
    page.insert_text((72, 72), "Learning Python", fontsize=24, fontname="hebo")
    page.insert_text((72, 120), "By Local Compiler", fontsize=14, fontname="helv")
    
    page.insert_text((72, 200), "Table of Contents", fontsize=16, fontname="hebo")
    page.insert_text((72, 240), "Chapter 1: Getting Started", fontsize=12, fontname="hebo")
    page.insert_text((90, 260), "1.1 Installation", fontsize=11, fontname="helv")
    page.insert_text((90, 280), "1.2 Hello World", fontsize=11, fontname="helv")
    
    page.insert_text((72, 320), "Chapter 2: Variables", fontsize=12, fontname="hebo")
    page.insert_text((90, 340), "2.1 Data Types", fontsize=11, fontname="helv")
    page.insert_text((90, 360), "2.2 Operators", fontsize=11, fontname="helv")

    # Page 2: Chapter 1 text
    page = doc.new_page()
    page.insert_text((72, 72), "Chapter 1 Getting Started", fontsize=16, fontname="hebo")
    page.insert_text((72, 110), "1.1 Installation", fontsize=12, fontname="hebo")
    page.insert_text((72, 130), "To install Python, download the installer from python.org and run it.", fontsize=11, fontname="helv")
    
    page.insert_text((72, 200), "1.2 Hello World", fontsize=12, fontname="hebo")
    page.insert_text((72, 220), "You can run your first program using print('Hello World') in your editor.", fontsize=11, fontname="helv")

    # Page 3: Chapter 2 text
    page = doc.new_page()
    page.insert_text((72, 72), "Chapter 2 Variables", fontsize=16, fontname="hebo")
    page.insert_text((72, 110), "2.1 Data Types", fontsize=12, fontname="hebo")
    page.insert_text((72, 130), "Python has several built-in data types such as integers, floats, and strings.", fontsize=11, fontname="helv")
    
    page.insert_text((72, 200), "2.2 Operators", fontsize=12, fontname="hebo")
    page.insert_text((72, 220), "Python supports arithmetic operators like addition, subtraction, multiplication, and division.", fontsize=11, fontname="helv")

    doc.save(filename)
    doc.close()
    print(f"[+] Test PDF created successfully at {filename}")

if __name__ == "__main__":
    create_pdf()
