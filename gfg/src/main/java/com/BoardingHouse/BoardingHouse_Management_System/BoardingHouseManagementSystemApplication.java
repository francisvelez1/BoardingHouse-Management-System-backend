package com.BoardingHouse.BoardingHouse_Management_System;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoardingHouseManagementSystemApplication {

	public static void main(String[] args) {
		SpringApplication.run(BoardingHouseManagementSystemApplication.class, args);
		System.out.println(
				"Welcome to the Boarding House Management System! This application helps you manage your boarding house efficiently. You can add tenants, manage rooms, and keep track of payments all in one place. Let's get started!");
	}
}
