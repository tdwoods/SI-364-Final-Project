import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from flask import Flask, render_template, session, redirect, request, url_for, flash
from flask_script import Manager, Shell
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FileField, PasswordField, BooleanField, SelectMultipleField, ValidationError
from wtforms.validators import Required, Length, Email, Regexp, EqualTo
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate, MigrateCommand
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_required, logout_user, login_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash

#App Setup
app = Flask(__name__)
app.debug = True
app.use_reloader = True
app.config['SECRET_KEY'] = 'who would ever guess this really hard string for my final project 364?'
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get('DATABASE_URL') or "postgresql://localhost/tdwoods364final"
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['HEROKU_ON'] = os.environ.get('HEROKU')

#Database Manager
manager = Manager(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
manager.add_command('db', MigrateCommand)

#Login Manager
login_manager = LoginManager()
login_manager.session_protection = 'strong'
login_manager.login_view = 'login'
login_manager.init_app(app)

#Spotify Manager
client_credentials_manager = SpotifyClientCredentials(client_id='d34f7439910849f5b39739a6ac026ef9',client_secret='9da6f99891f04b31940a7b3b95f96954')
spotify = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

#########################
######## Models #########
#########################
user_playlist = db.Table('user_playlists',
    db.Column('song_id', db.Integer, db.ForeignKey('songs.id')),
    db.Column('playlist_id', db.Integer, db.ForeignKey('playlists.id')))

song_recommendation = db.Table('song_recommendations',
    db.Column('song_id', db.Integer, db.ForeignKey('songs.id')),
    db.Column('recommendation_id', db.Integer, db.ForeignKey('recommendations.id')))

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key = True)
    email = db.Column(db.String(64), unique = True, index = True)
    username = db.Column(db.String(255), unique = True, index = True)
    password_hash = db.Column(db.String(128))
    playlists = db.relationship('Playlist', backref = 'users', lazy='dynamic')

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

class Song(db.Model):
    __tablename__ = 'songs'
    id = db.Column(db.Integer, primary_key = True)
    title = db.Column(db.String())
    artist = db.Column(db.String())
    album = db.Column(db.String())
    album_cover_url = db.Column(db.String())
    duration = db.Column(db.String())
    external_url = db.Column(db.String())
    track_id = db.Column(db.String())

class Playlist(db.Model):
    __tablename__ = 'playlists'
    id = db.Column(db.Integer, primary_key = True)
    name = db.Column(db.String(64), unique = True)
    user = db.Column(db.Integer, db.ForeignKey('users.id'))
    songs = db.relationship('Song', secondary = user_playlist, backref = db.backref('playlists',lazy = 'dynamic'), lazy = 'dynamic')

class Recommendation(db.Model):
    __tablename__ = 'recommendations'
    id = db.Column(db.Integer, primary_key = True)
    name = db.Column(db.String(64), unique = True)
    songs = db.relationship('Song', secondary = song_recommendation, backref = db.backref('recommendations',lazy= 'dynamic'), lazy = 'dynamic')

#Login user_loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

#########################
### Helper Functions ####
#########################
def get_song_by_id(id):
    return Song.query.filter_by(id = id).first()

def get_or_create_song(title, artist):
    song = Song.query.filter_by(title = title, artist = artist).first()
    if not song:
        spotify_data = spotify_search(title + ", " + artist)
        title = spotify_data['tracks']['items'][0]['name']
        artist = spotify_data['tracks']['items'][0]['artists'][0]['name']
        album = spotify_data['tracks']['items'][0]['album']['name']
        album_cover = spotify_data['tracks']['items'][0]['album']['images'][1]['url']
        secs = spotify_data['tracks']['items'][0]['duration_ms'] / 1000
        mins = int(secs / 60)
        secs = int(secs % 60)
        if secs < 10:
            secs = '0' + str(secs)
        duration = "{}:{}".format(mins,secs)
        external_url = spotify_data['tracks']['items'][0]['external_urls']['spotify']
        track_id = spotify_data['tracks']['items'][0]['id']
        song = Song(title = title, artist = artist, album = album, album_cover_url = album_cover, duration = duration, external_url = external_url, track_id = track_id)
        db.session.add(song)
        db.session.commit()
    return song

def get_or_create_playlist(name, current_user, song_list = []):
    playlist = current_user.playlists.filter_by(name=name).first()
    if not playlist:
        playlist = Playlist(name = name)
        current_user.playlists.append(playlist)
        for song in song_list:
            playlist.songs.append(song)
        db.session.add(current_user)
        db.session.add(playlist)
        db.session.commit()
    return playlist


def get_or_create_recommendation(name, song_list = []):
    recommendation = recommendation.query.filter_by(name = name).first()
    if not recommendation:
        recommendation = recommendation(name = name)
        for song in song_list:
            recommendation.songs.append(song)
        db.session.add(recommendation)
        db.session.commit()
    return recommendation

def spotify_search(query):
    try:
        data = spotify.search(q = query, type = 'track', limit = 1)
        return data
    except:
        return False

#########################
######### Forms #########
#########################
def validate_search_query(form, field):
    if ',' not in field.data:
        raise ValidationError('Query not formatted correctly: <title>, <artist>')
    results = spotify_search(field.data)
    if results is False or len(results['tracks']['items']) == 0:
        raise ValidationError('Spotify did not return any data on your song')
    title = results['tracks']['items'][0]['name']
    artist = results['tracks']['items'][0]['artists'][0]['name']
    query = Song.query.filter_by(title = title, artist = artist).first()
    if query:
        raise ValidationError('Song already exists in database')

def validate_name(form, field):
    if isinstance(form, PlaylistForm) or isinstance(form, UpdatePlaylistForm):
        result = Playlist.query.filter_by(name=field.data).first()
    else:
        result = Recommendation.query.filter_by(name=field.data).first()
    if result is not None:
        raise ValidationError("Name already taken")

class RegistrationForm(FlaskForm):
    email = StringField('Enter email: ', validators = [Required(), Length(1,64), Email()])
    username = StringField('Enter username: ', validators = [Required(), Regexp('^[\w._]*$', 0, 'Usernames can only contain letter, number, underscores, periods'), Length(1,64)])
    password = PasswordField('Enter password: ', validators = [Required(), Length(8,128), EqualTo('confirm_password', message="your passwords must match")])
    confirm_password = PasswordField("Confirm Password: ", validators = [Required()])
    submit = SubmitField('Register User')

    def validate_username(self,field):
        if User.query.filter_by(username = field.data).first():
            raise ValidationError('Username already taken')

    def validate_email(self,field):
        if User.query.filter_by(email = field.data).first():
            raise ValidationError('User already registered with that email')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[Required(), Length(1,64), Email()])
    password = PasswordField('Password', validators=[Required(), Length(8,128)])
    stay_signed_in = BooleanField('Keep me logged in')
    submit = SubmitField('Log In')

class SongForm(FlaskForm):
    search_query = StringField('Enter song to search (ex: Yellow Submarine, Beatles): ', validators = [Required(), validate_search_query])
    submit = SubmitField('Search')

class PlaylistForm(FlaskForm):
    name = StringField('Enter name of Playlist: ', validators = [Required(), validate_name])
    songs = SelectMultipleField('Songs to include: ',validators = [Required()], coerce = int)
    submit = SubmitField('Submit')

class RecommendationForm(FlaskForm):
    name = StringField('Enter name of recommendation list: ', validators = [Required(), validate_name])
    songs = SelectMultipleField('Songs to include: ', validators = [Required()])
    submit = SubmitField('Submit')

class UpdateButtonForm(FlaskForm):
    submit = SubmitField('Update')

class UpdatePlaylistForm(FlaskForm):
    name = StringField("Change the name of this playlist: ", validators = [validate_name])
    add_songs = SelectMultipleField('Select songs to add to playlist: ',coerce=int)
    remove_songs = SelectMultipleField('Select songs to remove from playlist: ',coerce=int)
    submit = SubmitField('Submit')

class DeleteButtonForm(FlaskForm):
    submit = SubmitField('Delete')

#########################
######## Routes #########
#########################
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.route('/register', methods = ["GET","POST"])
def register():
    r_form = RegistrationForm()
    if r_form.validate_on_submit():
        new_user = User(email = r_form.email.data, username = r_form.username.data, password = r_form.password.data)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))

    error_list = [error for error in r_form.errors.values()]
    for error in error_list:
        flash("Error in form submission: " + str(error[0]))

    return render_template('registration.html', form = r_form)

@app.route('/login', methods = ["GET","POST"])
def login():
    l_form = LoginForm()
    if l_form.validate_on_submit():
        current_user = User.query.filter_by(email = l_form.email.data).first()
        if current_user.verify_password(l_form.password.data) and current_user is not None:
            login_user(current_user, l_form.stay_signed_in.data)
            return redirect(url_for('index') or request.args.get('next'))
        flash('Invalid username or password.')

    error_list = [error for error in l_form.errors.values()]
    for error in error_list:
        flash("Error in form submission: " + str(error[0]))

    return render_template('login.html', form = l_form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out')
    return redirect(url_for('index'))

@app.route('/', methods = ["GET","POST"])
def index():
    s_form = SongForm()
    if s_form.validate_on_submit():
        data = s_form.search_query.data.split(",")
        title = data[0]
        artist = data[1]
        get_or_create_song(title, artist)
        flash('Added song successfully')
        return redirect('/')

    error_list = [error for error in s_form.errors.values()]
    for error in error_list:
        flash("Error in form submission: " + str(error[0]))
    return render_template('base.html', form = s_form)

@app.route('/all_songs')
def all_songs():
    song_list = Song.query.all()
    return render_template('all_songs.html', songs = song_list)

@app.route('/create_playlist', methods = ['GET', 'POST'])
@login_required
def create_playlist():
    p_form = PlaylistForm()
    song_choices = [(song.id, song.title + " by " + song.artist) for song in Song.query.all()]
    p_form.songs.choices = song_choices
    if p_form.validate_on_submit():
        song_list = [get_song_by_id(id) for id in p_form.songs.data]
        playlist = get_or_create_playlist(name = p_form.name.data, current_user = current_user, song_list = song_list)
        return redirect(url_for("view_playlist", playlist_name = playlist.name))
    return render_template("create_playlist.html", form = p_form)

@app.route('/all_playlists')
@login_required
def all_playlists():
    all_playlists = current_user.playlists.all()
    u_form = UpdateButtonForm()
    d_form = DeleteButtonForm()
    return render_template('all_playlists.html', playlists = all_playlists, u_form = u_form, d_form = d_form)

@app.route('/view_playlist/<playlist_name>')
@login_required
def view_playlist(playlist_name):
    playlist = get_or_create_playlist(name = playlist_name, current_user = current_user)
    return render_template("view_playlist.html", playlist = playlist)

@app.route('/update_playlist/<playlist_name>', methods = ['GET', 'POST'])
def update_playlist(playlist_name):
    u_form = UpdatePlaylistForm(request.args)
    playlist = get_or_create_playlist(name = playlist_name, current_user = current_user)
    add_song_choices = [(song.id, song.title + ' by ' + song.artist) for song in Song.query.all() if song not in playlist.songs.all()]
    remove_song_choices = [(song.id, song.title + ' by ' + song.artist) for song in playlist.songs.all()]
    u_form.add_songs.choices = add_song_choices
    u_form.remove_songs.choices = remove_song_choices
    if u_form.validate():
        if request.args['name'] == "":
            playlist.name = playlist_name
        else:
            playlist.name = request.args['name']
        remove_songs = [get_song_by_id(id) for id in request.args.get('remove_songs', [])]
        add_songs = [get_song_by_id(id) for id in request.args.get('add_songs', [])]
        for song in remove_songs: playlist.songs.remove(song)
        for song in add_songs: playlist.songs.append(song)
        db.session.add(playlist)
        db.session.commit()
        if playlist_name == playlist.name:
            flash('Updated playlist {}'.format(playlist_name))
        else:
            flash('Updated playlist {} to {}'.format(playlist_name, playlist.name))
        return redirect("/all_playlists")

    error_list = [error for error in u_form.errors.values()]
    for error in error_list:
        flash("Error in form submission: " + str(error[0]))
    return render_template('update_playlist.html', playlist_name = playlist.name, form = u_form)

@app.route('/delete_playlist/<playlist_name>', methods = ['GET', 'POST'])
def delete_playlist(playlist_name):
    playlist = get_or_create_playlist(name = playlist_name, current_user = current_user)
    current_user.playlists.remove(playlist)
    db.session.add(current_user)
    db.session.delete(playlist)
    db.session.commit()
    flash('Deleted playlist: ' + playlist_name)
    return redirect("/all_playlists")

@app.route('/create_recommendation', methods = ['GET','POST'])
def create_recommendation():
    r_form = RecommendationForm()
    song_choices = [(song.track_id, song.title + ' by ' + song.artist) for song in Song.query.all()]
    r_form.songs.choices = song_choices
    if r_form.validate_on_submit():
        recommendation = Recommendation(name = r_form.name.data)
        spotify_data = spotify.recommendations(seed_tracks = r_form.songs.data, limit = 5)
        for s in spotify_data['tracks']:
            title = s['name']
            artist = s['artists'][0]['name']
            album = s['album']['name']
            album_cover = s['album']['images'][1]['url']
            secs = s['duration_ms'] / 1000
            mins = int(secs / 60)
            secs = int(secs % 60)
            if secs < 10:
                secs = '0' + str(secs)
            duration = "{}:{}".format(mins,secs)
            external_url = s['external_urls']['spotify']
            track_id = s['id']
            song = Song(title = title, artist = artist, album = album, album_cover_url = album_cover, duration = duration, external_url = external_url, track_id = track_id)
            recommendation.songs.append(song)
        db.session.add(recommendation)
        db.session.commit()
        return redirect(url_for('view_recommendation', recommendation_id = recommendation.id))

    error_list = [error for error in r_form.errors.values()]
    for error in error_list:
        flash("Error in form submission: " + str(error[0]))
    return render_template("create_recommendation.html", form = r_form)

@app.route('/view_recommendation/<recommendation_id>')
def view_recommendation(recommendation_id):
    all_songs = Song.query.all()
    recommendation = Recommendation.query.filter_by(id = int(recommendation_id)).first()
    return render_template('view_recommendation.html', recommendation = recommendation, all_songs = all_songs)

@app.route('/all_recommendations')
def all_recommendations():
    recommendations = Recommendation.query.all()
    return render_template('all_recommendations.html', recommendations = recommendations)

if __name__ == '__main__':
    db.create_all()
    manager.run()
