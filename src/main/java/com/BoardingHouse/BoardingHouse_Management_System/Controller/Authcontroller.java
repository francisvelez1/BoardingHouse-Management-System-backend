package com.BoardingHouse.BoardingHouse_Management_System.Controller;

import com.BoardingHouse.BoardingHouse_Management_System.service.auth.AuthenticationService;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/auth")
public class Authcontroller {

    private final AuthenticationService authenticationService;

    public Authcontroller(AuthenticationService authenticationService) {
        this.authenticationService = authenticationService;
    }

    @PostMapping("/login")
    public ResponseEntity<?> login(@RequestBody Map<String, String> loginRequest) {
        String username = loginRequest.get("username");
        String password = loginRequest.get("password");

        try {
            // Utilizes your service to authenticate and store the session
            Authentication auth = authenticationService.authenticate(username, password);
            return ResponseEntity.ok(Map.of("message", "Login successful", "user", auth.getName()));
        } catch (Exception e) {
            return ResponseEntity.status(401).body(Map.of("error", "Invalid credentials"));
        }
    }
}