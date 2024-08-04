from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import uuid
import os

app = Flask(__name__)
app.secret_key = 'osho'

data_dir = 'data'
if not os.path.exists(data_dir):
    os.makedirs(data_dir)

def get_db_connection():
    conn = sqlite3.connect('askai.db', check_same_thread=False)
    
    cursor = conn.cursor()
    return conn, cursor

def create_tables():
    conn, cursor = get_db_connection()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS tenants (
                        tenant_id TEXT PRIMARY KEY,
                        tenant_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        user_name TEXT NOT NULL,
                        email TEXT NOT NULL,
                        password TEXT NOT NULL,
                        role TEXT DEFAULT 'user',
                        tenant_id TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS documents (
                        document_id TEXT PRIMARY KEY,
                        document_name TEXT,
                        document_type TEXT,
                        document_path TEXT,
                        tenant_id TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS questions (
                        question_id TEXT PRIMARY KEY,
                        question_content TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        tenant_id TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id),
                        FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS answers (
                        answer_id TEXT PRIMARY KEY,
                        answer_content TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        question_id TEXT NOT NULL,
                        tenant_id TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id),
                        FOREIGN KEY (question_id) REFERENCES questions(question_id),
                        FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS history (
                        history_id TEXT PRIMARY KEY,
                        action TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        affected_id TEXT NOT NULL,
                        affected_type TEXT NOT NULL,
                        tenant_id TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id),
                        FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                    )''')
    
    conn.commit()
    conn.close()

@app.route('/')
def index():
    if is_logged_in():
        if session['role'] == 'admin':
            return render_template('index.html', username=session['username'])
        else:
            return redirect(url_for('tenant_data', tenant_id=session['tenant_id']))
    else:
        return redirect(url_for('login'))
    
@app.route('/create_tables')
def create_tables_route():
    create_tables()
    return redirect(url_for('login'))
    

@app.route('/login', methods=['GET'])
def login_form():
    if is_logged_in():
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/register', methods=['GET'])
def register_form():
    if is_logged_in():
        return redirect(url_for('index'))
    return render_template('register.html')


@app.route('/about_us', methods=['GET'])
def about_us():
    return render_template('about_us.html', username=session.get('username'))


@app.route('/load_documents/<tenant_id>', methods=['GET'])
def load_documents(tenant_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    user_role = session.get('role')
    if user_role == 'admin':
        home_url = '/'
    else:
        home_url = '/tenant_data/' + tenant_id
    conn, cursor = get_db_connection()
    cursor.execute('''SELECT * FROM tenants WHERE tenant_id = ?''', (tenant_id,))
    tenant = cursor.fetchone()
    conn.close()
    tenant_dict = {'tenant_id': tenant[0], 'tenant_name': tenant[1], 'created_at': tenant[2], 'updated_at': tenant[3]}
    return render_template('load_documents.html', username=session.get('username'), tenant=tenant_dict, home_url=home_url)


@app.route('/register', methods=['POST'])
def register():
    username = request.form['username']
    email = request.form['email']
    password = generate_password_hash(request.form['password'])
    tenant_id = request.form['tenant_id']
    user_id = str(uuid.uuid4())
    conn, cursor = get_db_connection()
    user = cursor.execute('''SELECT * FROM users WHERE tenant_id = ?''', (tenant_id,)).fetchone()
    if user is not None:
        return render_template('register.html', message='Tenant already has a user')
    result = cursor.execute('''INSERT INTO users (user_id, user_name, email, password, tenant_id) VALUES (?, ?, ?, ?, ?)''', (user_id, username, email, password, tenant_id))
    conn.commit()
    conn.close()
    if result:
        session['username'] = username
        session['user_id'] = user_id
        session['tenant_id'] = tenant_id
        session['role'] = 'user'
    if is_logged_in():
        if session['role'] == 'user':
            return redirect(url_for('tenant_data', tenant_id=tenant_id))
    return jsonify({'message': 'User registered successfully'}), 201

# create admin user
@app.route('/seed')
def seed():
    conn, cursor = get_db_connection()
    admin = cursor.execute('''SELECT * FROM users WHERE user_name = ?''', ('admin',))
    if admin.fetchone() is not None:
        return redirect(url_for('login'))
    cursor.execute('''INSERT INTO tenants (tenant_id, tenant_name) VALUES (?, ?)''', ('1', 'admin'))
    result = cursor.execute('''INSERT INTO users (user_id, user_name, email, password, tenant_id, role) VALUES (?, ?, ?, ?, ?, ?)''', ('1', 'admin', 'admin@gmail.com', generate_password_hash('admin'), '1', 'admin'))
    conn.commit()
    conn.close()
    if result:
        return redirect(url_for('login'))
    return jsonify({'message': 'Admin user created successfully'}), 201


@app.route('/login', methods=['POST'])
def login():
    if is_logged_in():
        return redirect(url_for('index'))
    username = request.form['username']
    password = request.form['password']
    conn, cursor = get_db_connection()
    user = cursor.execute('''SELECT * FROM users WHERE user_name = ?''', (username,)).fetchone()
    conn.close()
    if user is not None and check_password_hash(user[3], password):
        session['username'] = username
        session['user_id'] = user[0]
        session['tenant_id'] = user[5]
        if user[4] == 'admin':
            session['role'] = 'admin'
            return redirect(url_for('index'))
        else:
            session['role'] = 'user'
            return redirect(url_for('tenant_data', tenant_id=user[5]))
    else:
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


def is_logged_in():
    return 'username' in session


@app.route('/add_tenant', methods=['POST'])
def add_tenant():
    if not is_logged_in():
        return redirect(url_for('login'))
    tenant_name = request.form['tenant_name']
    tenant_id = str(uuid.uuid4())
    conn, cursor = get_db_connection()
    cursor.execute('''INSERT INTO tenants (tenant_id, tenant_name) VALUES (?, ?)''', (tenant_id, tenant_name))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Tenant added successfully'}), 201


@app.route('/get_all_tenants', methods=['GET'])
def get_all_tenants():
    if not is_logged_in():
        return redirect(url_for('login'))
    conn, cursor = get_db_connection()
    cursor.execute('''SELECT tenant_id, tenant_name, created_at, updated_at FROM tenants WHERE tenant_name != 'admin';''')
    tenants = cursor.fetchall()
    conn.close()
    tenant_list = [{'tenant_id': t[0], 'tenant_name': t[1], 'created_at': t[2], 'updated_at': t[3]} for t in tenants]
    return jsonify(tenant_list), 200


@app.route('/edit_tenant/<tenant_id>', methods=['PUT'])
def edit_tenant(tenant_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    new_tenant_name = request.form['new_tenant_name']
    conn, cursor = get_db_connection()
    cursor.execute('''UPDATE tenants SET tenant_name = ?, updated_at = CURRENT_TIMESTAMP WHERE tenant_id = ?''', (new_tenant_name, tenant_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Tenant updated successfully'}), 200


@app.route('/delete_tenant/<tenant_id>', methods=['DELETE'])
def delete_tenant(tenant_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    conn, cursor = get_db_connection()
    cursor.execute('''DELETE FROM tenants WHERE tenant_id = ?''', (tenant_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Tenant deleted successfully'}), 200
    

@app.route('/tenant_data/<tenant_id>', methods=['GET'])
def tenant_data(tenant_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    user_role = session.get('role')
    if user_role == 'admin':
        home_url = '/'
    else:
        home_url = '/tenant_data/' + tenant_id
    conn, cursor = get_db_connection()
    cursor.execute('''SELECT * FROM tenants WHERE tenant_id = ?''', (tenant_id,))
    tenant = cursor.fetchone()
    conn.close()
    if tenant is None:
        return render_template('tenant_data.html', message='Tenant not found', username=session['username'], home_url=home_url, tenant=tenant)
    else:
        tenant_dict = {'tenant_id': tenant[0], 'tenant_name': tenant[1], 'created_at': tenant[2], 'updated_at': tenant[3]}
        return render_template('tenant_data.html', tenant=tenant_dict, username=session['username'], user_profile_url='/get_user/'+session['user_id'],  home_url=home_url, base_path=os.path.dirname(os.path.abspath(__file__)))
    

@app.route('/documents/<tenant_id>', methods=['GET'])
def get_documents(tenant_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    conn, cursor = get_db_connection()
    tenant = cursor.execute('''SELECT * FROM tenants WHERE tenant_id = ?''', (tenant_id,))
    if tenant.fetchone() is None:
        return render_template('tenant_data', message='Tenant not found')
    cursor.execute('''SELECT * FROM documents WHERE tenant_id = ?''', (tenant_id,))
    documents = cursor.fetchall()
    conn.close()
    document_list = [{'document_id': d[0], 'document_name': d[1], 'document_type': d[2], 'document_path': '\\'+d[3], 'created_at': d[5], 'updated_at': d[6]} for d in documents]
    return jsonify(document_list), 200


@app.route('/add_document/<tenant_id>', methods=['POST'])
def add_document(tenant_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    
    if tenant_id is None:
        return jsonify({'message': 'Tenant ID is required'}), 400
    
    if 'files[]' not in request.files:
        return {"error": "No file part in the request."}, 400
    
    files = request.files.getlist('files[]')
    if not files:
        return jsonify({'message': 'No files provided'}), 400
    
    tenant_dir = os.path.join(data_dir, tenant_id)
    docs_dir = os.path.join(tenant_dir, 'docs')
    raw_dir = os.path.join(docs_dir, 'raw')
    if not os.path.exists(raw_dir):
        os.makedirs(raw_dir)

    for file in files:

        # Extract document_id from the filename
        filename = secure_filename(file.filename)
        parts = filename.split('_')
        if len(parts) < 2:
            return jsonify({'error': 'Invalid filename format'}), 400
        
        document_id = parts[0]
        document_name = '_'.join(parts[1:])
        file_extension = filename.split('.')[-1]
        full_filename = f'{document_id}.{file_extension}'

        mime_type = file.content_type
        document_path = os.path.join(raw_dir, full_filename)
        file.save(document_path)
        conn, cursor = get_db_connection()
        cursor.execute('''INSERT INTO documents (document_id, document_name, document_type, document_path, tenant_id) VALUES (?, ?, ?, ?, ?)''', (document_id, document_name, mime_type, document_path, tenant_id))
        conn.commit()
        conn.close()
    return jsonify({'message': 'Document added successfully'}), 201


@app.route('/delete_document/<document_id>', methods=['DELETE'])
def delete_document(document_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    conn, cursor = get_db_connection()
    cursor.execute('''DELETE FROM documents WHERE document_id = ?''', (document_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Document deleted successfully'}), 200


@app.route('/view_document/<document_id>/tenant/<tenant_id>', methods=['GET'])
def view_document(document_id, tenant_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    conn, cursor = get_db_connection()
    cursor.execute('''SELECT * FROM documents WHERE document_id = ? AND tenant_id = ?''', (document_id, tenant_id))
    document = cursor.fetchone()
    conn.close()
    if document is None:
        return render_template('tenant_data', message='Document not found')
    mimetype = document[2]
    if mimetype.startswith('application/pdf'):
        file_extension = 'pdf'
    elif mimetype.startswith('text/plain'):
        file_extension = 'txt'

    # Construct the file path based on the provided information
    file_path = os.path.join('data', tenant_id, 'docs', 'raw', f'{document_id}.{file_extension}')
    if not os.path.exists(file_path):
        return 'File not found', 404
    
    # Send the file using Flask's send_file function
    return send_file(file_path, as_attachment=False)


# Route for getting all users (for admin)
@app.route('/users', methods=['GET'])
def get_all_users():
    if not is_logged_in() or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    # Connect to the database
    conn, cursor = get_db_connection()
    # Retrieve all users from the database
    cursor.execute('''SELECT * FROM users''')
    users = cursor.fetchall()
    conn.close()
    
    # Construct user list
    user_list = []
    for user in users:
        user_info = {
            'user_id': user[0],
            'user_name': user[1],
            'email': user[2],
            'role': user[4],
            'tenant_id': user[5],
            'created_at': user[6],
            'updated_at': user[7]
        }
        user_list.append(user_info)
    
    return render_template('user_data.html', users=user_list, username=session['username'])


@app.route('/get_user/<user_id>', methods=['GET'])
def get_user(user_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    
    conn, cursor = get_db_connection()
    user = cursor.execute('''SELECT * FROM users WHERE user_id = ?''', (user_id,)).fetchone()
    conn.close()
    if user is None:
        return jsonify({'message': 'User not found'}), 404
    
    user_info = {
        'user_id': user[0],
        'user_name': user[1],
        'email': user[2],
        'role': user[4],
        'tenant_id': user[5],
        'created_at': user[6],
        'updated_at': user[7]
    }
    return render_template('user_profile.html', user=user_info)


# Route for deleting a user
@app.route('/delete_user/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    if not is_logged_in() or session['role'] != 'admin':
        return jsonify({'message': 'Unauthorized access'}), 401
    
    # Connect to the database
    conn, cursor = get_db_connection()
    
    # Check if the user exists
    user = cursor.execute('''SELECT * FROM users WHERE user_id = ?''', (user_id,)).fetchone()
    if user is None:
        conn.close()
        return jsonify({'message': 'User not found'}), 404
    
    # Delete the user
    cursor.execute('''DELETE FROM users WHERE user_id = ?''', (user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'User deleted successfully'}), 200

    
if __name__ == '__main__':
    app.run(debug=True)