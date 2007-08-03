from elixir import *
from elixir.ext.versioned import acts_as_versioned
from datetime import datetime, timedelta

import time


def setup():
    global Director, Movie, Actor

    class Director(Entity):
        has_field('name', Unicode(60))
        has_many('movies', of_kind='Movie', inverse='director')
        using_options(tablename='directors')


    class Movie(Entity):
        has_field('id', Integer, primary_key=True)
        has_field('title', Unicode(60), primary_key=True)
        has_field('description', Unicode(512))
        has_field('releasedate', DateTime)
        belongs_to('director', of_kind='Director', inverse='movies')
        has_and_belongs_to_many('actors', of_kind='Actor', inverse='movies', tablename='movie_casting')
        using_options(tablename='movies')
        acts_as_versioned()


    class Actor(Entity):
        has_field('name', Unicode(60))
        has_and_belongs_to_many('movies', of_kind='Movie', inverse='actors', tablename='movie_casting')
        using_options(tablename='actors')

    metadata.bind = 'sqlite:///'


def teardown():
    cleanup_all()


class TestVersioning(object):
    def setup(self):
        create_all()
    
    def teardown(self):
        drop_all()
        objectstore.clear()
    
    def test_versioning(self):    
        gilliam = Director(name='Terry Gilliam')
        monkeys = Movie(id=1, title='12 Monkeys', description='draft description', director=gilliam)
        bruce = Actor(name='Bruce Willis', movies=[monkeys])
        objectstore.flush(); objectstore.clear()
    
        time.sleep(1)
        after_create = datetime.now()
        time.sleep(1)
    
        movie = Movie.get_by(title='12 Monkeys')
        assert movie.version == 1
        assert movie.title == '12 Monkeys'
        assert movie.director.name == 'Terry Gilliam'
        movie.description = 'description two'
        objectstore.flush(); objectstore.clear()
    
        time.sleep(1)
        after_update_one = datetime.now()
        time.sleep(1)
    
        movie = Movie.get_by(title='12 Monkeys')
        movie.description = 'description three'
        objectstore.flush(); objectstore.clear()
    
        time.sleep(1)
        after_update_two = datetime.now()
        time.sleep(1)
    
        movie = Movie.get_by(title='12 Monkeys')
        oldest_version = movie.get_as_of(after_create)
        middle_version = movie.get_as_of(after_update_one)
        latest_version = movie.get_as_of(after_update_two)
    
        initial_timestamp = oldest_version.timestamp
    
        assert oldest_version.version == 1
        assert oldest_version.description == 'draft description'
    
        assert middle_version.version == 2
        assert middle_version.description == 'description two'
    
        assert latest_version.version == 3
        assert latest_version.description == 'description three'
    
        differences = latest_version.compare_with(oldest_version)
        assert differences['description'] == ('description three', 'draft description')
    
        assert len(movie.versions) == 2
        assert movie.versions[0] == oldest_version
        assert movie.versions[1] == middle_version
    
        movie.revert_to(1)
        objectstore.flush(); objectstore.clear()
    
        movie = Movie.get_by(title='12 Monkeys')
        assert movie.version == 1
        assert movie.timestamp == initial_timestamp
        assert movie.title == '12 Monkeys'
        assert movie.director.name == 'Terry Gilliam'