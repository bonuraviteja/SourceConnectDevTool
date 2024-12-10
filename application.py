import pyodbc
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os
import uuid
import sqlparse

# Database connection details
db_config = {
    "server": "10.72.145.13",
    "database": "INFOR_ONPREM_DB",
    "username": "sa",
    "password": "4Magnitude",
    "driver": "SQL Server",
}

output_dir = "C:/Users/lakshmi.prasanna/OneDrive - insightsoftware/Documents/TEMPLATES_SC_SOURCES/inforLn/scripts"

def clean_object_name(name):
    """Remove square brackets and schema from the object name."""
    # Remove brackets and schema part (everything before and including the dot)
    name = name.strip('[]')
    name = name.split('.')[-1]  # Get the part after the dot (if any)
    return name

def format_sql(sql_content):
    #formatted = sqlparse.format(sql_content, reindent=True, keyword_case='upper')
    # Remove extra blank lines
    lines = sql_content.splitlines()
    trimmed_lines = [line.strip() for line in lines if line.strip()]  # Remove empty or whitespace-only lines
    return "\n".join(trimmed_lines)

def fetch_object_definitions(object_names, object_type):
    """Fetch DDL definitions for tables, views, or procedures."""
    try:
        conn = pyodbc.connect(
            f"DRIVER={db_config['driver']};"
            f"SERVER={db_config['server']};"
            f"DATABASE={db_config['database']};"
            f"UID={db_config['username']};"
            f"PWD={db_config['password']}"
        )
        cursor = conn.cursor()
        object_definitions = []

        for object_name in object_names:
            if object_type == "VIEW":
                # Fetch DDL for each view
                cursor.execute(f"""
                    SELECT upper(v.name) AS ObjectName, LTRIM(m.definition) AS Definition, 'VIEW' AS ObjectType
                    FROM sys.views v
                    INNER JOIN sys.sql_modules m ON v.object_id = m.object_id
                    WHERE v.name = ?
                """, object_name)
            elif object_type == "PROCEDURE":
                # Fetch DDL for each stored procedure
                cursor.execute(f"""
                    SELECT upper(p.name) AS ObjectName, LTRIM(m.definition) AS Definition, 'PROCEDURE' AS ObjectType
                    FROM sys.procedures p
                    INNER JOIN sys.sql_modules m ON p.object_id = m.object_id
                    WHERE p.name = ?
                """, object_name)
            else:
                # Fetch DDL for each table (can keep existing logic or add more logic as needed)
                cursor.execute(f"""EXEC table_ddl ?, 'dbo' """, object_name)

            rows = cursor.fetchall()
            for row in rows:
                # Clean up the object name and the definition
                cleaned_name = clean_object_name(row.ObjectName)
                #cleaned_name = row.ObjectName
                definition = row.Definition
                if row.ObjectType == "VIEW":
                    definition = definition.replace("CREATE   VIEW", "CREATE OR ALTER VIEW").replace("CREATE     VIEW","CREATE OR ALTER VIEW").replace("CREATE    VIEW","CREATE OR ALTER VIEW")
                    definition = definition.replace(f"[{row.ObjectName}]", cleaned_name)
                    definition = definition.replace("[dbo].", '')
                elif row.ObjectType == "PROCEDURE":
                    definition = definition.replace("CREATE   PROCEDURE", "CREATE OR ALTER PROCEDURE").replace("CREATE     PROCEDURE","CREATE OR ALTER PROCEDURE").replace("CREATE    PROCEDURE","CREATE OR ALTER PROCEDURE")
                    definition = definition.replace(f"[{row.ObjectName}]", cleaned_name)
                    definition = definition.replace("[dbo].", '')
                
                # Remove brackets from the object name in the definition
                #definition = definition.replace(f"[{row.ObjectName}]", cleaned_name)
                
                object_definitions.append({
                    "name": cleaned_name,
                    "definition": definition,
                    "type": row.ObjectType
                })

        conn.close()
        return object_definitions

    except Exception as e:
        print(f"Error fetching object definitions: {e}")
        return []

def prettify_xml(elem):
    """Return a formatted XML string with exactly one line between tags."""
    rough_string = ET.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty = reparsed.toprettyxml(indent="    ")

    # Remove unnecessary blank lines
    lines = pretty.split("\n")
    stripped_lines = [line for line in lines if line.strip()]  # Remove empty lines

    # Join the lines into a single string
    pretty_xml = "\n".join(stripped_lines)

    # Replace &lt; with < and &gt; with >
    pretty_xml = pretty_xml.replace("&lt;", "<").replace("&gt;", ">")
    pretty_xml = pretty_xml.replace("amp;", "")

    return pretty_xml

def update_or_add_object_to_xml(object_definitions, existing_file):
    """Update or add object definitions in the XML, preserving CDATA tags."""
    namespaces = {"xsi": "http://www.w3.org/2001/XMLSchema-instance"}
    ET.register_namespace("xsi", namespaces["xsi"])

    # Parse existing XML or create a new structure if the file doesn't exist
    if os.path.exists(existing_file):
        tree = ET.parse(existing_file)
        scripts = tree.getroot()
        template_items = scripts.find("./Scripts/MxScript/TemplateItems")
    else:
        scripts = ET.Element("Scripts")
        mx_script = ET.SubElement(scripts, "MxScript")
        template_items = ET.SubElement(mx_script, "TemplateItems")
        print("Created new XML structure.")

    # Map existing objects by name for quick lookup
    existing_objects = {
        item.find("Name").text: item for item in template_items.findall("MxTemplateItem")
    }

    # Process each object definition
    for obj in object_definitions:
        file_name = os.path.join(output_dir, f"{obj['name'].upper()}.sql")
        with open(file_name, "w") as sql_file:
            sql_file.write(format_sql(obj['definition']))
        print(f"Generated {file_name}")
        if obj["name"] in existing_objects:
            # Update definition tags for the existing object
            existing_item = existing_objects[obj["name"]]
            raw_def_elem = existing_item.find("RawDefinition")
            def_elem = existing_item.find("Definition")

            if obj["type"] == "TABLE":
                # Update RawDefinition and keep Definition as is
                current_definition_content = def_elem.text if def_elem is not None else "<![CDATA[]]>"
                raw_def_elem.text = f"<![CDATA[{obj['definition']}]]>"
                def_elem.text = f"<![CDATA[{current_definition_content}]]>"
            else:
                # For views/procedures, update both RawDefinition and Definition
                raw_def_elem.text = f"<![CDATA[ ]]>"  # Keep RawDefinition updated
                def_elem.text = f"<![CDATA[{obj['definition']}]]>"  # Update the Definition tag

            print(f"Updated object: {obj['name']} ({obj['type']})")

        else:
            # If the object doesn't exist, add it as a new MxTemplateItem
            item = ET.SubElement(template_items, "MxTemplateItem", {
                "{http://www.w3.org/2001/XMLSchema-instance}type": "MxTableItem" if obj["type"] == "TABLE" else "MxViewItem" if obj["type"] == "VIEW" else "MxProcedureItem"
            })
            ET.SubElement(item, "Uuid").text = str(uuid.uuid4())
            ET.SubElement(item, "Name").text = obj["name"].upper()
            
            # Ensure the CDATA wrapping for RawDefinition and Definition
            if obj["type"] == "TABLE":
                ET.SubElement(item, "RawDefinition").text = f"<![CDATA[{obj['definition']}]]>"
                ET.SubElement(item, "Definition").text = "<![CDATA[]]>"  # No definition content for tables
            else:
                ET.SubElement(item, "RawDefinition").text = "<![CDATA[]]>"  # No raw definition for views/procedures
                ET.SubElement(item, "Definition").text = f"<![CDATA[{obj['definition']}]]>"

            print(f"Added new object: {obj['name']} ({obj['type']})")
            
    for existing_item in existing_objects.values():
        raw_def_elem = existing_item.find("RawDefinition")
        def_elem = existing_item.find("Definition")

        # Check for the presence of the <RawDefinition> tag
        if raw_def_elem is not None:
            # If <RawDefinition> exists but is improperly formatted, fix it
            if raw_def_elem.text is None or not raw_def_elem.text.startswith("<![CDATA["):
                raw_def_elem.text = f"<![CDATA[{raw_def_elem.text}]]>"  # Ensure CDATA wrapping for valid content
        else:
            # If the opening tag is missing but the closing tag exists, recreate <RawDefinition>
            raw_def_elem = ET.SubElement(existing_item, "RawDefinition")
            raw_def_elem.text = f"<![CDATA[{raw_def_elem.text}]]>"  # Add an empty CDATA structure

        # Ensure <Definition> is similarly well-formed
        if def_elem is not None:
            if def_elem.text is None or not def_elem.text.startswith("<![CDATA["):
                def_elem.text = f"<![CDATA[{def_elem.text}]]>"  # Ensure CDATA wrapping for valid content
        else:
            # If <Definition> tag is completely missing, add it
            def_elem = ET.SubElement(existing_item, "Definition")
            def_elem.text = f"<![CDATA[{def_elem.text}]]>" # Add an empty CDATA structure

    

           # print(f"Ensured CDATA wrapping for existing object: {existing_item.find('Name').text}")

    # Prettify and save updated XML
    pretty_xml = prettify_xml(scripts)

    # Backup logic
    backup_file = existing_file + ".bak"
    if os.path.exists(backup_file):
        os.remove(backup_file)  # Remove existing backup
    os.rename(existing_file, backup_file)  # Create the backup

    with open(existing_file, "w", encoding="utf-8") as f:
        f.write(pretty_xml)

    print(f"XML file updated. Backup saved as: {backup_file}")




if __name__ == "__main__":
    # List of objects to process
    objects_to_process = [       
        {"name":"OT_LN_AR_VIEW","type":"VIEW"},       
        {"name":"CDC_TRX_DATE","type":"TABLE"},
        {"name":"POP_STG","type":"PROCEDURE"},
        {"name":"OT_LN_VIEW","type":"VIEW"},
        {"name":"CDC_LN_VIEW","type":"VIEW"},
                
    ]

    # Fetch DDL definitions for these objects
    object_definitions = []
    for obj in objects_to_process:
        definitions = fetch_object_definitions([obj["name"]], obj["type"])
        object_definitions.extend(definitions)

    if object_definitions:
        # Update existing XML file
        existing_file = "C:/Users/lakshmi.prasanna/OneDrive - insightsoftware/Documents/TEMPLATES_SC_SOURCES/inforLn/DEC_CHANGES/Infor LN Azure SC Template/New folder/Infor LN Azure SC Template/Infor LN 10.4 MSSQL SC Template/Source/test_template.xml"
        update_or_add_object_to_xml(object_definitions, existing_file)
    else:
        print("No object definitions retrieved.")
  


  #the scenarios to be covered 

  #1. when ever there is any update in the existing view ,defination has to be updation ,keeping raw defination empty 
  #2. when ever there is any new object (table,view,procedure) that object has to be created in the xml with proper tags and all 
  #3. in case of  new object table the raw definition has to get updated ,leaving the definition tag emtpy which later need to be filled by content to drop or create or just skip if exists 
  #4. in case of old table object the raw defination has to be updated leaving the defination tag remain same
  #5. need to check sync feature and all 


  #to view list of views in database 
#   SELECT '{"name":"'+upper(v.name)+'","type":"VIEW"},' ObjectName
#                     FROM sys.views v
#                     INNER JOIN sys.sql_modules m ON v.object_id = m.object_id  order by v.modify_date desc
#                    -- WHERE v.name = ?


#to view list of procedures in databse 

#  SELECT upper(p.name) as name,'{"name":"'+upper(p.name)+'","type":"PROCEDURE"},' ObjectName,p.modify_date as modified_date
#                    FROM sys.procedures p
#                     INNER JOIN sys.sql_modules m ON p.object_id = m.object_id  order by p.modify_date desc
#                    -- WHERE p.name = ?


#to view list of tables in database
# SELECT upper(TABLE_NAME) as name,'{"name":"'+upper(TABLE_NAME)+'","type":"TABLE"},' ObjectName
#                    FROM INFORMATION_SCHEMA.TABLES
#    WHERE TABLE_TYPE = 'BASE TABLE'
# ORDER BY TABLE_SCHEMA, TABLE_NAME;

