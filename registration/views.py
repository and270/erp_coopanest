from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from .forms import CustomUserCreationForm, CustomUserLoginForm

def login_register_view(request):
    if request.method == 'POST':
        if 'register' in request.POST:
            register_form = CustomUserCreationForm(request.POST)
            login_form = CustomUserLoginForm()
            if register_form.is_valid():
                user = register_form.save()
                login(request, user)
                return redirect('home')  # Redirect to a homepage or dashboard
        elif 'login' in request.POST:
            login_form = CustomUserLoginForm(request, data=request.POST)
            register_form = CustomUserCreationForm()
            if login_form.is_valid():
                username = login_form.cleaned_data.get('username')
                password = login_form.cleaned_data.get('password')
                user = authenticate(username=username, password=password)
                if user is not None:
                    login(request, user)
                    return redirect('home')  # Redirect to a homepage or dashboard
    else:
        register_form = CustomUserCreationForm()
        login_form = CustomUserLoginForm()

    return render(request, 'login_register.html', {
        'register_form': register_form,
        'login_form': login_form,
    })

