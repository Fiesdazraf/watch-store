function make { 
    python manage.py makemigrations @args 
}

function mig { 
    python manage.py migrate @args 
}

function run { 
    python manage.py runserver @args 
}

function shell { 
    python manage.py shell @args 
}

function test {
    pytest @args
}

function check { 
    python manage.py check @args 
}

function pre { 
    pre-commit run --all-files @args 
}
